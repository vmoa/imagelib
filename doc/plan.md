# Imagelib Work Plan

## Phase 1 — Fix Discovered Issues

### Bugs (4)

1. `fitsfiles.py` — pass the `Fitsdb` instance explicitly into `addFitsFile()` rather than relying on the global name reassignment; the current code works by accident
2. `catalog.py:169` — replace `next` (a Python built-in, not a loop keyword) with `continue`; malformed catalog lines are currently silently accepted
3. `markup.py` — remove the `{% if messages %}` guard that prevents flashed error messages from ever rendering
4. `fitsfiles.py` — initialize `temp_safe_preview` and `temp_safe_thumb` to `None` before the `try` block so the `finally` clause doesn't risk `NameError`

### Security (3)

5. `markup.py:74` — fix SQL injection in the fuzzy LIKE query: refactor `where_list` to carry bound values alongside the clause strings, and use parameterized queries throughout
6. `markup.py:71` — use parameterized queries for the exact-match path as well
7. `__init__.py` — load `secret_key` from an environment variable or a file outside the repo instead of hardcoding it

### Structural (2)

8. `catalog.py:31` — move the `Fitsdb` connection out of the class-level body and into lazy initialization in `cname()`; importing `catalog` currently opens a DB connection as a side effect
9. `fitsdb.py` — remove the unused `execute_and_commit()` method

### Code Quality (7)

10. `markup.py` — convert all `print()` calls to `logging.debug()` / `logging.info()`
11. `__init__.py` — remove `"DEBUG:"` prefix from INFO-level log messages; replace `print()` request logging with `app.logger.debug()`
12. `fitsfiles.py` — replace `os.popen()` and `os.system()` with `subprocess`; `subprocess` is already imported and used in `fits2png()`
13. `markup.py:276` — remove redundant `zip.close()` after the `with` block
14. `markup.py:238` — remove the dead `preview` field from the pic dict
15. `catalog.py:218` — rename `type` variable to avoid shadowing the built-in
16. `catalog.py:96` — wrap `open(catalogfile)` in `with`

### HTML/JS (5)

17. `imagelib.html` — replace `<image>` with `<img>` (two occurrences)
18. `imagelib.html` — replace deprecated `<font color=...>` with a CSS-styled `<span>`
19. `imagelib.js` — fix `toggleSelect()` signature to accept the mode argument that is already being passed
20. `imagelib.js` — replace deprecated `event.keyCode` with `event.key`
21. `imagelib.js` / `catalog.py` — fix typos (`"Wuery"`, `"help.hmtl"`, `"Reutrn"`)

---

## Phase 2 — Test Infrastructure

### Framework and structure

- `pytest` with a `tests/` directory; no test runner currently exists
- `requirements-dev.txt` for test dependencies (`pytest`, `pytest-flask`, `pytest-cov`)
- GitHub Actions workflow at `.github/workflows/test.yml` that installs dependencies, runs the suite, and reports coverage on every push and pull request; `fitspng` will be mocked since it is a native binary

### Unit tests

- `fitsdb.py`: table creation, insert, duplicate rejection, `status` query against an in-memory SQLite database
- `fitsfiles.py`: `parseFitsHeader()` with a minimal synthetic FITS file (standard `.fits`) and a Rice-compressed `.fits.fz` file, `buildDatabaseRecord()` for both calibration and target image types, the filename extension normalization logic in `fits2png()` (subprocess mocked)
- `catalog.py`: `prettyspace()`, `cname()` against a populated test catalog, the `next`→`continue` fix verifies that malformed lines are actually skipped
- `markup.py`: `buildWhere_imgfilter()`, `buildWhere_target()` exact and fuzzy paths (including the SQL injection fix), `findStartDate()`, `zipit()` with real temp files

### Integration tests

- Flask test client covering all six routes: `/`, `/search`, `/download`, `/deets`, `/fits/<path>`, `/Eagle/<path>`
- Full round-trip: ingest a synthetic FITS file → query DB → render template → verify rendered HTML contains expected target name
- Download flow: select records → ZIP is returned with correct filenames and in both `.fits.fz` and `.fits` format options (Phase 3c)

---

## Phase 3 — Asterism Integration and Rice Compression Support

### Background

Asterism (formerly Science Scheduler, first-light-systems.com) is a cloud-hosted observatory scheduling platform. The Asterism NINA plugin captures images at RFO, sends them to Asterism's pipeline, which calibrates and annotates each image adding organization and project tags in the FITS header, then produces Rice-compressed `.fits.fz` files that are delivered to imagelib via SCP.

### 3a — File delivery via SCP

**Decision**: SCP chosen over the Asterism REST API. The REST API has no timestamp-based filtering on any list endpoint, requiring full pagination on every hourly run. SCP is zero new code: the existing cron job scans `/home/nas/Eagle/` via `find -newer tsfile` and picks up files in any subdirectory automatically.

**Drop point**: `/home/nas/Eagle/Asterism/rfo/`

**Server setup** (AWS imagelib host):

1. Create the Asterism system account (no login shell, no home directory):
   ```bash
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin asterism
   ```

2. Create the drop directory:
   ```bash
   sudo mkdir -p /home/nas/Eagle/Asterism/rfo
   sudo chown asterism:nas /home/nas/Eagle/Asterism/rfo
   sudo chmod 2775 /home/nas/Eagle/Asterism/rfo
   ```
   The imagelib cron runs as a user in the `nas` group and inherits read access from the group.

3. Install Asterism's public key, restricted to SCP-only writes to the drop directory:
   ```
   command="scp -t /home/nas/Eagle/Asterism/rfo",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty <ASTERISM_PUBLIC_KEY>
   ```

4. Verify: SCP a test `.fits.fz` from a local machine as the `asterism` user and confirm the next cron run ingests it.

### 3b — fits.fz ingestion support

**Status: committed in `95f7e3c`**

**Verified** (`verify_fitspng_fz.py`, 2026-06-13):
- `parseFitsHeader()` works on `.fits.fz` unchanged — astropy's `CompImageHDU` presents correct dimensions.
- `fitspng` accepts `.fits.fz` directly via cfitsio transparent decompression.
- The temp-rename workaround in `fits2png()` works for `.fits.fz` without modification.

**Changes made**:
- `fits2png()` extension handling: replaced hardcoded `[:-5]` strip with explicit branch on extension (also fixes pre-existing `.fit` bug); temp-rename now preserves original extension.
- `fitsdb.py`: added `FITSDB_FILE` env var override for test DB isolation.
- Tests: `test_fits2png_fitsz_preview_and_thumb_created`, `test_fits2png_fitsz_original_file_restored`, fixed `test_malformed_catalog_line_skipped` to pass `FITSDB_FILE` to subprocess.

**No `compressed` column**: compression is inferred from `path` ending in `.fits.fz` wherever needed; no DB column required.

### 3c — Download format choice

- **UI**: add a format radio button (`.fits.fz` / `.fits`) to the download form; show it only when the current page contains at least one `.fits.fz` file (determined by inspecting `path` values in the query result); default to `.fits.fz`.
- **`markup.py` `zipit(fmt='fz')`**: accept a `fmt` parameter; when `fmt='fits'` and the source file ends in `.fits.fz`, decompress in memory using `astropy.io.fits` before writing to the ZIP. Stored files are never modified.
- **`__init__.py` `/download` route**: read the `fmt` form field and pass it to `zipit()`.
- **Tests**:
  - Unskip and implement `test_download_format_choice` in `tests/test_routes.py`: seed a `.fits.fz` record; POST with `fmt=fits` → ZIP contains `.fits`; POST with `fmt=fz` → ZIP contains `.fits.fz`.
  - Add to `tests/test_markup.py`: `test_zipit_fitsz_served_as_fz` (pass-through unchanged) and `test_zipit_fitsz_decompressed_to_fits` (produces valid readable `.fits`).

### 3d — RFO calibration filter

**Decision**: imagelib will ignore uncalibrated images from RFO telescopes going forward; only calibrated images will be processed.

All RFO images are prefixed `MN` (uppercase); calibrated ones are prefixed `MNc` (uppercase MN, lowercase c). Change takes effect from deploy; existing rows and image files are left unchanged.

**Change**: in `fitsfiles.py` `addFitsFile()`, add at the top:
```python
basename = os.path.basename(filename)
if basename.startswith('MN') and not basename.startswith('MNc'):
    logging.info(f"Skipping uncalibrated RFO image: {filename}")
    return 0
```

### 3e — Organization, project, observatory, observer metadata

**New FITS header fields from Asterism** (full list received; subset stored in this phase):

| FITS keyword | Description | Stored |
|---|---|---|
| `SSPROJ` | Project name (human readable) | yes → `project` |
| `INSTABBR` | Abbreviated org/inst name | yes → `organization` |
| `OBSERVAT` | Observatory name (standard keyword) | yes → `observatory` |
| `OBSERVER` | Observer name (standard keyword) | yes → `observer` |
| `SSPROJID` | Project ID (internal) | no |
| `SSORG` | Organization full name | no |
| `SSOVSVID` | Observatory ID (internal) | no |
| `SSOBSID` | Observation ID (internal) | no |
| `OBSNAME` | Observation name | no |
| `OBSEMAIL` | Observer email | no |
| `PRIORITY` | Priority number | no |

**Database**: add four nullable TEXT columns to `fits`: `organization`, `project`, `observatory`, `observer`. Add `fitsdb.py update:orgproject` migration command for existing DBs (ALTER TABLE ADD COLUMN for each; existing rows get NULL).

**Null-handling rules by image source**:

| Source | `organization` | `project` | `observatory` | `observer` |
|---|---|---|---|---|
| Asterism light frame | `INSTABBR` header value | `SSPROJ` header value | `OBSERVAT` header value | `OBSERVER` header value |
| Calibration frame | NULL | NULL | NULL | NULL |
| Direct-from-RFO (non-Asterism) | `"RFO"` (default) | NULL | `OBSERVAT` header value (typically `"RFO-RC20"`) | `OBSERVER` header value (or NULL if absent) |

**Search UI**: three new `<select>` dropdowns on the search form:
- Org + project combined: distinct `(organization, project)` pairs; option value `"org|project"`; route handler splits on `|` and filters `WHERE organization = ? AND project = ?`.
- Observatory: distinct `observatory` values; filters `WHERE observatory = ?`.
- Observer: distinct `observer` values; filters `WHERE observer = ?`.

**Changes**: `fitsdb.py` (schema + migration), `fitsfiles.py` `parseFitsHeader()` + `buildDatabaseRecord()`, `markup.py` (dropdown data builders + `buildWhere_orgproject()`/`buildWhere_observatory()`/`buildWhere_observer()`), `__init__.py` routes, `imagelib.html`, tests.

### 3f — Version bump

Advance `VERSION` file from `v2.1.3` to `v3.1.0`.

### 3g — Asterism drop folder date-subfolder organization

**Requirement**: Asterism SFTP transfers arrive flat into `/home/nas/Eagle/Asterism/rfo/`. As the volume of files grows this will become unwieldy. Files must be moved into a `YYYY/MM/DD` nested subfolder tree (named from the `DATE-OBS` UTC date) during ingest. The three-level hierarchy keeps the inode count per folder low and makes manual browsing straightforward.

**Decision**: Use UTC date from the `DATE-OBS` FITS header. For most RFO observing sessions the session stays within a single UTC date, so this is consistent with how the UI already groups images. No noon-to-noon or local-time adjustment is applied.

**Implementation**: `fitsfiles.py` `_maybe_organize(filename, headers)` — called in `addFitsFile()` immediately after `parseFitsHeader()` returns, before `buildDatabaseRecord()` and before any DB insert. The method:
1. Checks whether the file's parent directory is exactly `ASTERISM_DROP` (`/home/nas/Eagle/Asterism/rfo`); if not, returns the path unchanged.
2. Splits `DATE-OBS[:10]` into `year`, `month`, `day`.
3. Creates `ASTERISM_DROP/YYYY/MM/DD/` if it doesn't exist (`os.makedirs(..., exist_ok=True)`).
4. Moves the file with `os.rename()` and returns the new path.

Because the move happens before the path is recorded in the database, the stored `path` is always the final date-subfolder location. Files already in a subfolder (i.e., the `find` command picks them up on a later run) are untouched since their parent directory won't match `ASTERISM_DROP`.

The `ASTERISM_DROP` constant is a class attribute on `FitsFiles`, overridable in tests.

**Tests**: 4 new tests in `test_fitsfiles.py` — move + dir creation, non-drop-folder no-op, already-organized file no-op.

---

## Production Deployment

### Overview

The production server is an AWS EC2 instance. All imagelib code, the SQLite database, and the FITS file store live under the `nas` user account:

| Path | Contents |
|---|---|
| `/home/nas/flask/imagelib/` | Git clone of the imagelib repo (branch: `master`) |
| `/home/nas/data/fits.db` | SQLite database |
| `/home/nas/Eagle/` | FITS file store (scanned hourly by cron) |
| `/home/nas/Eagle/Asterism/rfo/` | Asterism SCP drop point |

Apache serves the Flask app via `mod_wsgi`. Touching `imagelib.wsgi` causes mod_wsgi to reload the application on the next request — no Apache restart needed for code-only changes.

There is no staging environment. Validation is done by dropping a test FITS file, checking `/tmp/fitsfiles.out`, and exercising the UI.

### Deploy script

`bin/deploy.sh` in the repo is the canonical deploy procedure. It must run as the `nas` user:

```bash
sudo -u nas /home/nas/flask/imagelib/bin/deploy.sh
```

The script:
1. Backs up the code directory to `/tmp/imagelib-<timestamp>`
2. Stashes any uncommitted local changes (with a warning to review before discarding)
3. Runs `git pull`
4. Checks whether the `organization` column exists in the `fits` table; if not, prompts to run `fitsdb.py update:orgproject` (backs up the DB first)
5. Touches `imagelib.wsgi` to reload the app

### Handling production hotfixes

If the server has uncommitted local changes at deploy time (e.g., a hotfix applied directly to production), the script stashes them automatically and prints instructions to review the stash (`git stash show -p`) before dropping it. The expectation is that the pulled code incorporates all prior hotfixes; verify this before running `git stash drop`.

### Schema migrations

Migrations are interactive commands in `fitsdb.py`. The deploy script detects whether each migration is needed and offers to run it. If you decline, the command to run manually is printed. Migrations always back up the DB before altering the schema.

| Command | Adds | When needed |
|---|---|---|
| `python3 fitsdb.py update:orgproject` | `organization`, `project`, `observatory`, `observer` columns | Phase 3e deploy |

### First-time setup on a new server

```bash
git clone https://github.com/vmoa/imagelib /home/nas/flask/imagelib
cd /home/nas/flask/imagelib
python3 fitsdb.py create
# Install fitspng, configure Apache WSGI (see etc/100-imagelib.conf)
```

---

## Asterism SCP Key Installation

This is a one-time setup step performed on the AWS server to authorize Asterism to drop files via SCP. Asterism authenticates using an SSH key pair; BJ at Asterism holds the private key and provides the public key.

### Key choices

- Use the **Ed25519 public key** provided by BJ — it is more modern and secure than RSA.
- No password is set on the `asterism` account. Authentication is entirely via the key pair.
- The `command=` restriction in `authorized_keys` locks the account so the key can only be used to SCP files into the drop directory — no shell, no port forwarding, no reading files back.

### What to send BJ

Once the key is installed, give BJ:

- **Host**: `imagelib.rfo.org`
- **Username**: `asterism`
- **Destination path**: `/home/nas/Eagle/Asterism/rfo/`
- **Private key**: BJ already has it (it is the other half of the public key he sent)

BJ's SSH client will be prompted to accept `imagelib.rfo.org`'s host key on first connection — that is normal and expected.

### Installation steps

The `asterism` account was created with `--no-create-home`, so the `.ssh` directory must be created manually:

```bash
# 1. Create the home and .ssh directories
sudo mkdir -p /home/asterism/.ssh
sudo chown -R asterism: /home/asterism
sudo chmod 700 /home/asterism
sudo chmod 700 /home/asterism/.ssh

# 2. Point the user's passwd entry at the new home directory
sudo usermod --home /home/asterism asterism

# 3. Install the Ed25519 public key with SFTP-only restriction
#    internal-sftp is built into sshd — no external binary required
sudo tee /home/asterism/.ssh/authorized_keys <<'EOF'
command="internal-sftp",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKZKo+HxsGfAG58XOAbUeW8Nlhnibwaem6kBpQXRguef
EOF

# 4. Lock down permissions (sshd rejects world-readable authorized_keys)
sudo chown asterism: /home/asterism/.ssh/authorized_keys
sudo chmod 600 /home/asterism/.ssh/authorized_keys

# 5. Verify
sudo cat /home/asterism/.ssh/authorized_keys
```

Step 5 should show a single line beginning with `command="internal-sftp"` followed by the key.

### End-to-end verification

Ask BJ to SFTP a test `.fits.fz` file to `asterism@imagelib.rfo.org` into `/home/nas/Eagle/Asterism/rfo/` and confirm it appears in that directory. Then wait for the next hourly cron run (or trigger `python3 fitsfiles.py` manually) and check `/tmp/fitsfiles.out` to confirm the file was ingested.

---

## Phase 4 — SkyX FITS Compression and S3 Archival

### Background

NAS disk usage audit (2026-08): `Eagle` is 400 GB of the 492 GB NAS; `SkyX` is 328 GB of that (82%) and growing — 2026 alone logged 105 GB of `.fits` data through Aug 17, annualizing to ~169 GB, more than double 2024 or 2025. Of Eagle's other four folders: `Asterism` (1 GB) already arrives pre-compressed as `.fits.fz` (Phase 3b) and needs no work; `Maxim` (538 MB, 65 DB rows) and `Processed` (436 MB, 1 DB row) are unused islands pending a team decision on deletion; `NINA` (71 GB) has FITS files tracked in the database as well as their thumb.png and png files just like in SkyX.

Two strategies are being pursued for `SkyX/Images` and `NINA/Astro-Images`:
1. **Compress existing raw `.fits`/`.fit` files to `.fits.fz` in place** (RICE, lossless for integer data) — this phase. Note that this means that `.fit` files will be renamed `fits.fz` after compression. 
2. **Archive older years to S3**, keeping DB records intact and imagelib able to fetch on demand — design only so far, see 4c.

### 4a — Compression scope 

**Scope**: `db_scope.py` (ad hoc, not checked in) grouping DB rows by top-level folder under `Eagle` found 33,525 `fits` rows under `SkyX` (31,906 `.fits` + 1,619 `.fit`). Filesystem walk of `SkyX/Images` alone found 34,974 matching files (fits+fit+the one existing fits.fz) — a gap of ~1,449 against the DB row count. All files in the NINA folders were added to the database.  **the compression script should be driven by DB rows (`SELECT id, path FROM fits WHERE path LIKE '/home/nas/Eagle/SkyX/%.fits' OR path LIKE '/home/nas/Eagle/SkyX/%.fit', OR path LIKE '/home/nas/Eagle/NINA/%.fits'`), not by a filesystem walk** — every file it touches is then guaranteed to have a DB row to update.

### 4b — Compression findings (sample-based, see full data in the team doc)

Sampled up to 15 files per year per type, RICE-compressed via `astropy.io.fits.CompImageHDU` (same technique as `create_test_fitsz()` in `verify_fitspng_fz.py`), measured real before/after size:

| Year | Current (fits+fit) | Projected | Savings |
|---|---|---|---|
| 2021 | 3.71 GB | 2.18 GB | 41% |
| 2022 | 6.26 GB | 2.99 GB | 52% |
| 2023 | 21.38 GB | 10.53 GB | 51% |
| 2024 | 64.41 GB | 33.11 GB | 49% |
| 2025 | 48.21 GB | 17.92 GB | 63% |
| 2026 (YTD) | 105.35 GB | 46.82 GB | 56% |
| **Total** | **249.32 GB** | **113.55 GB** | **~54%** |

### 4c — Maintenance mode

Both the SkyX migration (4d) and the NINA follow-up (4e) rewrite `path`/`preview`/`thumbnail` values and move files on disk — a request served mid-migration could hit a stale path or a 404. Both need user access blocked for their full duration, so this is a shared prerequisite, not part of either migration script itself.

**Decision**: a Flask-level maintenance flag, checked in a `before_request` hook in `__init__.py`, returning a 503 with a short "under maintenance" message for all routes. Toggle via a flag file (e.g. `os.path.exists('/home/nas/data/MAINTENANCE')`) — consistent with the existing env-var-override pattern already used for `FITSDB_FILE` in `fitsdb.py`. No Apache config changes needed, and it's trivially reversible (delete the flag file, no restart required since it's checked per-request).

**Needs**: write the `before_request` hook in `__init__.py` — not yet done. Do this before either migration script, since both depend on it.

### 4d — Migration script design (SkyX and NINA: compression + reorganization)

Precedent to build from: `rename_calibrated_test.py` already does the DB-row-lookup + `os.rename` + `UPDATE fits SET path` pattern (for already-compressed Asterism files) with a `--dry-run` flag; `_maybe_organize()` (Phase 3g) already builds a `YYYY/MM/DD` destination from a FITS date and creates it with `os.makedirs(..., exist_ok=True)`. This script combines both patterns — since the migration already touches every row's `path` to add compression, doing the folder reorganization in the same pass avoids touching each row (and each file) twice. NOTE: we just deleted the rename_calibrated_test.py unstaged file from the repo, so it is not present and probably not recoverable.

Suggested flow per row:

1. Query candidate rows per 4a (DB-driven, not filesystem walk). Skip rows whose file is missing on disk (log, don't crash — see the 1,449-row gap above, there may be more surprises).
2. (no longer needed)
3. Open with `astropy.io.fits`, write a RICE-compressed `CompImageHDU` to a temp file (pattern: `verify_fitspng_fz.create_test_fitsz`), then **re-open the temp file and verify the decompressed data matches the original** (`np.array_equal`) before touching anything on disk permanently — do not delete the original on faith.
4. Compute the destination `YYYY/MM/DD` directory from the DB **`date` column** (see "Date source" below), creating it if needed.
5. Move the compressed temp file into that destination as `<stem>.fits.fz`, and move the existing `.png`/`-thumb.png` alongside it into the same destination (same stem, per `fits2png()`'s naming convention) — all three files for a capture land together in one move.
6. `UPDATE fits SET path = ?, preview = ?, thumbnail = ? WHERE id = ?` (three columns now, not just `path`), commit, *then* delete the original raw file. Keep file-op and DB-op ordering such that a crash mid-run leaves either "nothing changed" or "both changed," never "DB updated but files not moved" or vice versa.
7. Default to `--dry-run` (matches `rename_calibrated_test.py` convention). Log every action to a file — this will run over ~33K rows and needs to be auditable/resumable, not just console output.
8. Pilot on 2021 (smallest year, 491 fits + 1 fit) before scaling to 2024–2026 which hold the bulk of the data.
9. Requires the maintenance-mode flag (4c) active for the entire run.

No `compressed` DB column needed — same as Phase 3b, compression state is inferred from the `path` suffix.

**Date source**: use the DB **`date` column**, not the date currently embedded in the existing `SkyX/Images/YYYY-MM-DD/` folder name. These differ — e.g. the Tycho 1371 example (`id=1`) has folder date `2023-04-20` but DB `date` `2023-04-21`. This is systematic for RFO's evening sessions, not an occasional edge case: Pacific-time evenings are already the next UTC day almost immediately after sunset, and `date` is derived from `DATE-OBS` (UTC). Using the DB column matches what `markup.py` already groups the UI by, and matches the Asterism Phase 3g precedent (`_maybe_organize()` also derives from `DATE-OBS`). This will shift most files' folder placement by one day relative to their current folder name — expected and desired, since it brings physical storage in line with what the app already shows.

**Refactor opportunity**: extract the `YYYY/MM/DD` path-building logic out of `_maybe_organize()` into a shared helper (e.g. `year_month_day_path(date_str, base_dir)`) usable by both this script and the NINA follow-up (4e), rather than duplicating it.

### 4e — NINA/Astro-Images reorganization (separate follow-up)

**Scope**: `NINA/Astro-Images` currently has no subfolder structure at all — all 1,181 `.fits` files plus their 1,926 preview/thumbnail `.png` files sit flat in one directory (see `doc/nina_astro_images_preliminary.md`). Reorganize into the same `YYYY/MM/DD` structure as SkyX (4d) and Asterism (Phase 3g), using the DB `date` column as the source of truth — confirmed by the M 42 test insert during the recent DB-registration backfill, which showed the same local-filename-vs-UTC-`date` offset (`2025-12-17` in the filename, `2025-12-18` as the stored `date`).

**Update (Roger feedback, Aug 2026)**: Roger confirmed that NINA will stop delivering new files to this folder going forward. Agreed approach: **leave DB-tracked files in place for now** — don't delete or move any of the 1,181 already-ingested captures ahead of schedule — and defer their actual move into `YYYY/MM/DD` to this migration (4e) when it runs. 

**Decision**: run the full reorganization as its own migration, in its own maintenance window, separate from the SkyX compression+reorg pass (4d). SkyX is the larger, higher-stakes migration (33,525+ rows, plus the compression step); keeping NINA's simpler reorg-only pass (1,181 rows, no compression because it was already done) independent means each can be scheduled, tested, and rolled back on its own.

No compression involved here — straight file-move + DB path update, reusing the shared `YYYY/MM/DD` helper from 4d:
1. Query all `fits` rows where `path LIKE '/home/nas/Eagle/NINA/Astro-Images/%'`.
2. Compute destination `YYYY/MM/DD` from the DB `date` column, create the directory if needed. The files should all be moved to that structure in the `SkyX/Images` parent folder so that when the move is done, there is nothing left in the NINA folder.
3. Move the `.fits`/`.fit` file, its `.png`, and its `-thumb.png` together to the new location (same stem, same destination folder).
4. `UPDATE fits SET path = ?, preview = ?, thumbnail = ? WHERE id = ?`, commit.
5. `--dry-run` default, logged, pilot on one date first.
6. Requires the maintenance-mode flag (4c) active for the duration.

### 4f — S3 archival (design only, not started)

Disk space goal on 500GB attached storage for this instance is to stay below 80% of capacity. The files are all in /home/nas/Eagle/Asterism or /home/nas/Eagle/SkyX — these are almost certainly where an S3-fallback branch needs to go for archived files. Current thinking (from the team discussion, not yet validated against the actual route code):

- Keep `.png`/`-thumb.png` local always (small, needed for instant UI browsing).
- Move (ideally already-compressed) `.fits.fz` files to S3.
- Add nullable columns rather than overload `path` — following the exact pattern `fitsdb.py`'s `update:imagetype` and `update:orgproject` migrations already use (interactive confirm, `ALTER TABLE ADD COLUMN`, back up first): something like `fitsdb.py update:storage` adding `storage_backend TEXT DEFAULT 'local'` and `s3_key TEXT`.
- `/fits/<path>` (and wherever `zipit()`/download logic reads the file) branches on `storage_backend`: local read, or S3 `GetObject`/presigned URL for archived rows.

Needs: read the actual paths and `zipit()` code before finalizing this — the sketch above is a starting hypothesis, not a spec.

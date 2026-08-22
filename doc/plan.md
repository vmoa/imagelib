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

## Phase 4 — SkyX/NINA Compression, Reorganization, and S3 Archival

### Background

NAS disk usage audit (2026-08): `Eagle` is 400 GB of the 492 GB NAS; `SkyX` is 328 GB of that (82%) and growing — 2026 alone logged 105 GB of `.fits` data through Aug 17, annualizing to ~169 GB, more than double 2024 or 2025. Of Eagle's other four folders: `Asterism` (1 GB) already arrives pre-compressed as `.fits.fz` (Phase 3b) and needs no work; `Maxim` (538 MB, 65 DB rows) and `Processed` (436 MB, 1 DB row) are unused islands pending a team decision on deletion; `NINA` (71 GB) has FITS files tracked in the database as well as their thumb.png and png files just like in SkyX.

Three strategies are being pursued:
1. **Compress existing raw `.fits`/`.fit` files to `.fits.fz` in place** (RICE, lossless) and reorganize into `YYYY/MM/DD` subfolders — 4d (SkyX) and 4e (NINA).
2. **Move NINA/Astro-Images files into SkyX/Images** — NINA is decommissioned as a delivery folder; all RFO RC20 images go to SkyX/Images going forward, or to Asterism/rfo if processed through Asterism. The NINA migration (4e) is the last thing that touches that folder.
3. **Archive older months to S3** when local disk exceeds 80% — 4f.

### 4a — Compression scope

**Scope**: `db_scope.py` (ad hoc, not checked in) grouping DB rows by top-level folder under `Eagle` found 33,525 `fits` rows under `SkyX` (31,906 `.fits` + 1,619 `.fit`). Filesystem walk of `SkyX/Images` alone found 34,974 matching files (fits+fit+the one existing fits.fz) — a gap of ~1,449 against the DB row count. All files in the NINA folders were added to the database. **The compression script must be driven by DB rows (`SELECT id, path FROM fits WHERE path LIKE '/home/nas/Eagle/SkyX/%.fits' OR path LIKE '/home/nas/Eagle/SkyX/%.fit' OR path LIKE '/home/nas/Eagle/NINA/%.fits'`), not by a filesystem walk** — every file it touches is then guaranteed to have a DB row to update.

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

Both the SkyX migration (4d) and the NINA migration (4e) rewrite `path`/`preview`/`thumbnail` values and move files on disk — a request served mid-migration could hit a stale path or a 404. Both need user access blocked for their full duration. S3 archival (4f) has the same requirement. This is a shared prerequisite for all three.

**Implementation**: a `before_request` hook in `__init__.py` that checks for a flag file and returns a 503 with a short "under maintenance" message for all routes. Flag file path: `/home/nas/data/MAINTENANCE` (consistent with the env-var-override pattern already used for `FITSDB_FILE` in `fitsdb.py`). No Apache config changes needed; trivially reversible by deleting the flag file with no restart required.

**Flag file path override**: support `IMAGELIB_MAINTENANCE` env var for the flag file path so tests can use a temp path without touching `/home/nas/data/`.

**This must be the first PR in phase 4** — 4d, 4e, and 4f all depend on it.

### 4d — Migration script: SkyX compression + reorganization

Lives at `bin/compress_migrate.py`. Kept in the repo permanently so it can be reviewed if questions arise later about what the migration did.

**Shared helper**: extract `date_subpath(date_str, base_dir)` out of `fitsfiles.py`'s `_maybe_organize()` into a standalone function (in `fitsfiles.py` or a new `migrate_utils.py`) that builds `base_dir/YYYY/MM/DD` and creates it with `os.makedirs(..., exist_ok=True)`. Both `bin/compress_migrate.py` and `bin/nina_migrate.py` (4e) import this.

**Flow per row**:

1. Query candidate rows (DB-driven, not filesystem walk): `SELECT id, path, date, preview, thumbnail FROM fits WHERE (path LIKE '/home/nas/Eagle/SkyX/%.fits' OR path LIKE '/home/nas/Eagle/SkyX/%.fit') AND storage_backend = 'local'` (the `storage_backend` filter excludes any row already archived to S3 if 4f has run). Support `--year YYYY` to restrict to rows where `date LIKE 'YYYY-%'` — pilot 2021 before scaling.
2. If the source file is missing on disk: log at WARNING level, increment a skip counter, continue — do not crash.
3. Open with `astropy.io.fits` (`do_not_scale_image_data=True`), write a RICE-compressed `CompImageHDU` to a temp file in the same directory as the source (so `os.rename` is atomic within the same filesystem). Then **re-open the temp file and verify the decompressed pixel data matches the original via `np.array_equal`** — do not proceed if this fails.
4. Compute the destination `SkyX/Images/YYYY/MM/DD/` directory from the DB `date` column using `date_subpath()`.
5. Rename the temp `.fits.fz` file to `dest_dir/<stem>.fits.fz`. Move the existing `.png` and `-thumb.png` files alongside (same stem, same dest dir). All three moves happen before any DB write.
6. `UPDATE fits SET path = ?, preview = ?, thumbnail = ? WHERE id = ?`, commit. Then delete the original raw `.fits`/`.fit` file. Ordering: files moved → DB updated → original deleted. A crash between steps leaves either "nothing changed" (before step 5) or "files moved + DB updated, original still present" (between 5 and original delete) — both are recoverable.
7. Defaults to `--dry-run` (prints planned actions, makes no changes). `--apply` performs the migration. Log every action (source, dest, DB update) to a timestamped file under `/tmp/compress_migrate_<timestamp>.log`.
8. Prints a summary on exit: processed, skipped (missing), failed (data mismatch or move error).
9. Requires the maintenance flag file to exist; refuses to run without it (check at startup, not per-row).

**Date source**: DB `date` column (UTC, from `DATE-OBS`), not the folder name embedded in the existing `SkyX/Images/YYYY-MM-DD/` path. The two differ systematically — Pacific evening sessions are already the next UTC day immediately after sunset. Using the DB column matches how `markup.py` groups the UI and matches the Asterism precedent (`_maybe_organize()`).

No `compressed` DB column — compression state inferred from `path` suffix, same as Phase 3b.

### 4e — NINA/Astro-Images migration (separate maintenance window)

Lives at `bin/nina_migrate.py`. Reorg-only (no compression — NINA files are already `.fits`; they will be RICE-compressed as part of this move since they match the 4a scope query). Destination is `SkyX/Images/YYYY/MM/DD/` — NINA files are merged into the SkyX folder tree, not given their own tree, because NINA is decommissioned as a delivery folder and all future RFO RC20 images go to SkyX.

Flow mirrors 4d (compression + file move + DB update + original delete) with these differences:
- Source query: `path LIKE '/home/nas/Eagle/NINA/Astro-Images/%'`
- Destination base: `/home/nas/Eagle/SkyX/Images/`
- No `--year` filter needed (1,181 rows; run all in one window)
- `--pilot-date YYYY-MM-DD` flag: process only rows where `date = ?`, for a single-date dry-run on production before committing to the full migration

Run in its own maintenance window after 4d is complete and verified. When this migration finishes, `NINA/Astro-Images` should be empty of DB-tracked files (log any files with no DB row at WARNING). The NINA folder itself is left in place — imagelib simply stops processing it.

### 4f — S3 archival

**Trigger**: monthly review. If local disk usage exceeds 80% of capacity (`shutil.disk_usage('/home/nas').used / total > 0.80`), identify the oldest calendar month with at least one local `.fits.fz` row (across both `SkyX/Images` and `Asterism/rfo`) and archive all of that month's `.fits.fz` files to S3. Repeat until usage drops below 80% or no more eligible months remain.

**S3 bucket**: `rfo-imagelib-archive` (globally unique; if taken, fall back to `vmoa-imagelib-archive`). Create in `us-west-2` (closest AWS region to RFO in northern California). No versioning needed — these are archival copies of immutable FITS files.

**S3 storage class**: **S3 Standard-IA** (Infrequent Access). Millisecond retrieval (same as Standard), ~46% cheaper storage ($0.0125/GB/month vs $0.023), $0.01/GB retrieval fee. Alternative: **S3 Glacier Instant Retrieval** at $0.004/GB/month with $0.03/GB retrieval — saves more on storage but costs 3× per retrieval; use if downloads of archived files turn out to be very rare and cost optimization is a priority. Decision deferred until first archival run.

**S3 key structure**: strip `/home/nas/Eagle/` prefix and use the remainder as the S3 key. Example: `/home/nas/Eagle/SkyX/Images/2021/01/15/NGC891_300s.fits.fz` → `SkyX/Images/2021/01/15/NGC891_300s.fits.fz`. Preserves the folder structure, makes it auditable in the S3 console.

**IAM authentication**: IAM instance role (preferred over access keys — available on all AWS account tiers including non-profit). To check if the EC2 instance already has a role: `curl -s http://169.254.169.254/latest/meta-data/iam/info` — if it returns a JSON object with a `InstanceProfileArn`, a role is attached; if it returns a 404, one must be created and attached via the EC2 console (Actions → Security → Modify IAM role). The role needs one policy: `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on the `rfo-imagelib-archive` bucket ARN.

**Database schema**: add two nullable columns to `fits` via `fitsdb.py update:storage`:
- `storage_backend TEXT DEFAULT 'local'` — `'local'` or `'s3'`
- `s3_key TEXT` — the S3 object key (NULL for local rows)

**What gets archived**: `.fits.fz` files only. `.png` and `-thumb.png` files stay local always — they are small and needed for instant UI browsing.

**What stays local after archival**: the row in `fits` (unchanged except `storage_backend` and `s3_key`), and the `.png`/`-thumb.png` previews.

**Download behavior for archived files**: imagelib proxies the S3 stream — the user sees no difference. `zipit()` and `/fits/<path>` check `storage_backend`; if `'s3'`, call `boto3.client('s3').get_object(Bucket=..., Key=row['s3_key'])` and stream the response body directly into the ZIP or HTTP response. No local caching — always stream fresh from S3. EC2 bandwidth is not a constraint for this application.

**Archival script**: `bin/s3_archive.py`. Arguments: `--dry-run` (default), `--apply`. Logs to `/tmp/s3_archive_<timestamp>.log`. Requires the maintenance flag at startup (same as 4d/4e). Flow:
1. Check disk usage; exit with "below threshold" message if under 80%.
2. Find oldest calendar month with eligible local rows (both `SkyX` and `Asterism` paths, `storage_backend = 'local'`).
3. For each row in that month: upload `.fits.fz` to S3 with `StorageClass='STANDARD_IA'`, then `UPDATE fits SET storage_backend = 's3', s3_key = ? WHERE id = ?`, commit, then delete the local file.
4. Re-check disk usage; repeat for next-oldest month if still over 80%.

---

## Phase 4 — Tests

### 4c — Maintenance mode (`tests/test_routes.py`)

- `test_maintenance_mode_returns_503_all_routes` — parametrize over all six routes; create the flag file (using `IMAGELIB_MAINTENANCE` env override), verify every route returns 503.
- `test_maintenance_mode_inactive_routes_work` — no flag file present; verify the home route returns 200.

### 4d/4e — Migration helpers (`tests/test_migrate.py`, new file)

**`date_subpath()` helper**:
- `test_date_subpath_builds_correct_path` — `date_subpath('2021-01-15', '/base')` returns `/base/2021/01/15`.
- `test_date_subpath_creates_directory` — directory is created on disk.

**Compression and data verification**:
- `test_compress_fits_produces_valid_fitsz` — compress a synthetic `.fits` file (from `conftest.make_fits_file`), reopen the output, verify `np.array_equal(original_data, decompressed_data)`.
- `test_compress_data_verification_rejects_mismatch` — write a corrupt temp file (wrong pixel values), verify the verification step raises an exception rather than proceeding.

**`bin/compress_migrate.py` behavior** (subprocess or direct function call):
- `test_dry_run_makes_no_disk_changes` — with `--dry-run`, source file still exists, no `.fits.fz` created, no DB changes.
- `test_year_filter_restricts_rows` — seed rows for 2021 and 2022; `--year 2021 --dry-run` logs only 2021 rows.
- `test_skips_missing_file_without_crash` — seed a DB row whose file does not exist; script logs a WARNING and increments skip count without raising.
- `test_moves_preview_and_thumb_with_fits` — after apply, `.png` and `-thumb.png` appear in the destination alongside the `.fits.fz`.
- `test_db_updated_before_original_deleted` — mock `os.unlink`; assert DB row has new path before the mock is called.
- `test_original_deleted_after_db_commit` — after apply, source `.fits`/`.fit` file is gone.
- `test_refuses_to_run_without_maintenance_flag` — no flag file; script exits non-zero with an error message.

**`bin/nina_migrate.py` behavior**:
- `test_nina_files_move_to_skyx_images` — source path under `NINA/Astro-Images/`, destination under `SkyX/Images/YYYY/MM/DD/`.
- `test_pilot_date_filter` — `--pilot-date 2025-12-18` processes only that date's rows.

### 4f — S3 archival (`tests/test_s3_archive.py`, new file)

Uses `moto` to mock AWS (add `moto[s3]` to `requirements-dev.txt`).

**Disk usage trigger**:
- `test_no_archival_when_under_threshold` — mock disk usage at 75%; script exits without touching S3.
- `test_archival_triggered_when_over_threshold` — mock disk usage at 85%; archival proceeds.
- `test_oldest_month_selected_across_skyx_and_asterism` — seed rows in two months under two source paths; verify the script selects the globally oldest month, not per-folder oldest.

**Upload and DB update**:
- `test_s3_upload_uses_correct_key` — verify `put_object` is called with key matching `SkyX/Images/YYYY/MM/DD/filename.fits.fz`.
- `test_s3_upload_uses_standard_ia_storage_class` — verify `StorageClass='STANDARD_IA'` in the `put_object` call.
- `test_db_updated_to_s3_after_upload` — after apply, row has `storage_backend = 's3'` and `s3_key` set.
- `test_local_file_deleted_after_db_commit` — mock DB commit; verify `os.unlink` is called only after commit.

**Download proxy**:
- `test_zipit_proxies_s3_file` — seed an archived row (mock `get_object` returning known bytes); call `zipit()`; verify ZIP contains those bytes under the expected filename.
- `test_fits_route_proxies_s3_file` — GET `/fits/<path>` for an archived row; verify response body matches mock S3 content.

**`fitsdb.py update:storage` migration**:
- `test_update_storage_adds_columns` — run migration against an in-memory DB, verify `storage_backend` and `s3_key` columns exist with correct defaults.

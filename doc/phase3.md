# Phase 3 — Asterism Integration and .fits.fz Support

## Overview

Science Scheduler has been renamed **Asterism** (first-light-systems.com). The system is a cloud-hosted observatory scheduling platform. The NINA plugin captures images at RFO, runs them through Asterism's calibration and annotation pipeline, and produces Rice-compressed `.fits.fz` files. All new images ingested into imagelib from Asterism will be `.fits.fz` only; this format reduces storage costs and is handled transparently by astropy, fitspng, and cfitsio.

---

## 3a — File Delivery via SCP

### Decision

After evaluating the Asterism REST API against SCP drop-off, **SCP was chosen**. The REST API has no timestamp-based filtering on any list endpoint, which would require paginating through the entire file history on every hourly run. SCP is simpler, carries no token-rotation overhead, and Asterism's pipeline can deliver files directly without any new imagelib code.

**No new imagelib code is needed.** The existing hourly cron job scans `/home/nas/Eagle/` recursively via `find -newer tsfile`, so files placed in any subdirectory — including `Asterism/rfo/` — are picked up automatically. `FILE_PATTERNS` already includes `*.fits.fz`.

### Directory structure

```
/home/nas/Eagle/
└── Asterism/
    └── rfo/          ← Asterism drops .fits.fz files here
        └── YYYY-MM-DD/
            └── <target>/
                └── image.fits.fz
```

The `YYYY-MM-DD/<target>/` hierarchy is optional but recommended; the `find` command recurses regardless of depth. Agree the exact path template with BJ when setting up the Asterism project's folder structure variable (e.g. `$DATE/$TARGET`).

### Server setup (AWS imagelib host)

1. **Create the drop directory** and set ownership so the Asterism SSH user can write but not read existing files:
   ```bash
   sudo mkdir -p /home/nas/Eagle/Asterism/rfo
   sudo chown asterism:nas /home/nas/Eagle/Asterism/rfo
   sudo chmod 1733 /home/nas/Eagle/Asterism/rfo   # write+execute, sticky; no read
   ```
   The imagelib cron runs as a user in the `nas` group and inherits read access from the group.

2. **Create the Asterism system account** (no login shell, no home directory):
   ```bash
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin asterism
   ```

3. **Install Asterism's public key** and restrict it to SCP-only, locked to the drop directory:
   ```
   # /home/asterism/.ssh/authorized_keys  (or /etc/ssh/authorized_keys/asterism)
   command="scp -t /home/nas/Eagle/Asterism/rfo",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty <ASTERISM_PUBLIC_KEY>
   ```
   The `command=` override means any SSH connection from this key can only write to the drop directory; it cannot open a shell, forward ports, or read files back.

4. **Test deposit point** to give BJ:
   - Host: `imagelib.rfo.org` (or the EC2 public hostname if DNS not yet pointed)
   - User: `asterism`
   - Path: `/home/nas/Eagle/Asterism/rfo/`
   - Key: exchange the Asterism service's public key via email; install as above

5. **Verify end-to-end** by SCP-ing a test `.fits.fz` from a local machine as the `asterism` user and confirming the next cron run ingests it.

---

## 3b — .fits.fz Ingestion Support  ✓ COMPLETE

**Committed in:** `95f7e3c` (Phase 3b: fix .fits.fz extension handling in fits2png and test isolation)

### Changes made

**`fitsfiles.py` — `fits2png()` extension handling**

The original code used a hardcoded `[:-5]` strip to build preview and thumbnail paths. This produced wrong paths for `.fits.fz` (leaving `.fi` in the stem) and also for `.fit` files (a pre-existing bug). Replaced with explicit branch on extension:

```python
if fits_path_abs.endswith('.fits.fz'):
    stem, temp_ext = fits_path_abs[:-8], '.fits.fz'
elif fits_path_abs.endswith('.fits'):
    stem, temp_ext = fits_path_abs[:-5], '.fits'
else:   # .fit
    stem, temp_ext = fits_path_abs[:-4], '.fit'
preview_final_abs = stem + '.png'
thumb_final_abs   = stem + '-thumb.png'
temp_safe_fits_path = os.path.join(fits_dir, 'temp_safe_image' + temp_ext)
```

The temp-rename file now preserves the original extension so cfitsio correctly identifies Rice-compressed data.

**`fitsdb.py` — `FITSDB_FILE` environment variable**

Added `FITSDB_FILE` env var override (same pattern as `IMAGELIB_SECRET_KEY`) so subprocesses spawned during testing use an isolated DB rather than the developer's local `fits.db`. Follows the same pattern as `IMAGELIB_SECRET_KEY` in `__init__.py`.

**Tests added**

- `test_fits2png_fitsz_preview_and_thumb_created` — verifies correct stem for `.fits.fz`
- `test_fits2png_fitsz_original_file_restored` — verifies temp-rename is always undone
- `test_malformed_catalog_line_skipped` — fixed to pass `FITSDB_FILE` to subprocess; removed unused monkeypatch and dead `db` variable

---

## 3c — Download Format Choice

### Decision

Users must be able to download either the original `.fits.fz` or a decompressed `.fits`. Astrophotography software (PixInsight, Sequence Generator Pro) handles `.fits.fz` natively; general-purpose tools may not. The decompressed `.fits` option is required for broad compatibility.

Decompression is performed in memory using `astropy.io.fits` — no `funpack` binary dependency, no disk writes, no modification to stored files.

### Implementation plan

**`markup.py` — `zipit(fmt='fz')`**

Add a `fmt` parameter to `zipit()`. When `fmt='fits'` and the source file ends in `.fits.fz`, decompress in memory before writing to the ZIP:

```python
import io

def zipit(self, recids, fmt='fz'):
    ...
    for record in records:
        path = record['path']
        arcname = os.path.basename(path)
        if fmt == 'fits' and path.endswith('.fits.fz'):
            arcname = arcname[:-3]   # strip .fz → .fits
            from astropy.io import fits as astrofits
            buf = io.BytesIO()
            with astrofits.open(path) as hdul:
                decompressed = astrofits.HDUList()
                for hdu in hdul:
                    if isinstance(hdu, astrofits.CompImageHDU):
                        decompressed.append(
                            astrofits.ImageHDU(data=hdu.data, header=hdu.header)
                        )
                    else:
                        decompressed.append(hdu)
                decompressed.writeto(buf)
            zf.writestr(arcname, buf.getvalue())
        else:
            zf.write(path, arcname)
    ...
```

**`__init__.py` — `/download` route**

Read the `fmt` form field and pass it to `zipit()`:

```python
fmt = request.form.get('fmt', 'fz')   # default: serve as-is
zip_path = markup.zipit(recids, fmt=fmt)
```

**`imagelib.html` — download form**

Add a format radio button that appears only when the page contains compressed files. Hide it (or default to `.fits.fz`) when there are no compressed files:

```html
<label><input type="radio" name="fmt" value="fz" checked> Download as .fits.fz</label>
<label><input type="radio" name="fmt" value="fits"> Download as .fits (decompressed)</label>
```

**`tests/test_routes.py` — implement skipped test**

Remove `@pytest.mark.skip` from `test_download_format_choice` and implement:
- Seed a `.fits.fz` record
- POST to `/download` with `fmt=fits` — assert ZIP contains `.fits` (not `.fits.fz`)
- POST to `/download` with `fmt=fz` — assert ZIP contains `.fits.fz`

**`tests/test_markup.py` — add `zipit` format tests**

- `test_zipit_fitsz_served_as_fz` — default `fmt='fz'` passes `.fits.fz` through unchanged
- `test_zipit_fitsz_decompressed_to_fits` — `fmt='fits'` produces a valid, readable `.fits` file in the ZIP

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

1. Don't assume. Don't hide confusion. Surface tradeoffs.

2. Minimum code that solves the problem. Nothing speculative.

3. Touch only what you must. Clean up only your own mess.

4. Define success criteria. Loop until verified.

## What This Is

Flask web application for browsing and downloading FITS astronomical images captured at RFO (Robert Ferguson Observatory). Served at https://imagelib.rfo.org with Apache WSGI and HTTP basic auth.

## Development Commands

```bash
# Setup (one-time)
virtualenv venv && . ./venv/bin/activate
pip install Flask astropy
# fitspng must be installed separately: apt-get install fitspng (Ubuntu) or build from source (macOS)
# Awesomplete JS library must be cloned into static/awesomplete/

# Run in development
flask --debug --app __init__.py run   # Serves on 0.0.0.0:5000

# Database management
python3 fitsdb.py create              # Initialize fresh database
python3 fitsdb.py status              # Show database stats

# Rebuild database from scratch (see REBUILD.md)
python3 fitsfiles.py                  # Scan for FITS files and insert into DB
python3 fitsfiles.py --debug          # Verbose mode
python3 fitsfiles.py --forcepng       # Regenerate PNG previews even if they exist
python3 fitsfiles.py --fitspath /path # Override default FITS directory

# Catalog
python3 catalog.py create <sac_file>  # Load SAC astronomy catalog
python3 catalog.py query <name>       # Test object name lookup

# Template debugging
python3 markup.py --debug
```

No automated test suite exists. Testing is manual via the Flask debug server.

## Architecture

Data flows through four layers:

1. **File ingestion** (`fitsfiles.py`): Cron job runs hourly (`etc/crontab.nas`). Scans `/home/nas/Eagle/` for new `.fits` files, parses FITS headers with `astropy`, calls `fitspng` CLI to generate a full-res preview PNG and a thumbnail (scaling factor = `x_pixels / 128 + 1`), then inserts metadata into SQLite.

2. **Database** (`fitsdb.py`): SQLite3 wrapper (no ORM). Three main tables: `fits` (image metadata), `fits_by_target` (denormalized for fast queries), `catalog`/`catalog_by_target` (SAC object name lookup). CLI commands for create/status/update. Dev DB lives in CWD; production DB at `/home/nas/data/`.

3. **Template context** (`markup.py`): Builds paginated, filtered data structures passed to Jinja2. Handles imagetype filtering (`cal`/`tgt`), target/date filtering, and ZIP download manifest assembly.

4. **Web server** (`__init__.py`): Six Flask routes — `/` (home), `/search`, `/download` (serves ZIP), `/deets` (image details), `/fits/<path>` and `/Eagle/<path>` (file serving).

**Key quirk**: `fitsfiles.py` temporarily renames FITS files to a simple name before calling `fitspng` to avoid issues with complex filenames, then renames back. See `fits2png()`.

## Production Deployment

Apache WSGI via `imagelib.wsgi`. Config in `etc/100-imagelib.conf`. App root: `/home/nas/flask/imagelib/`. The `secret_key` in `__init__.py` is hardcoded and should stay consistent between deploys (not randomized per restart).

## Database Schema

```sql
fits(id, target, object, date, timestamp, filter, binning, exposure, x, y,
     path, preview, thumbnail, imagetype)
-- imagetype: "cal" = calibration frame, "tgt" = science target
```

`target` is the canonical name (Messier numbers preferred, resolved via `catalog.py`); `object` is the raw FITS header value.

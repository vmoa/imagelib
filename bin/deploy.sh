#!/usr/bin/env bash
# Deploy imagelib to production from the current git branch.
# Must run as the nas user: sudo -u nas bin/deploy.sh

set -euo pipefail

REPO=/home/nas/flask/imagelib
DB=/home/nas/data/fits.db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    echo "Usage: sudo -u nas $0"
    echo ""
    echo "Deploys imagelib to production:"
    echo "  - backs up the code directory to /tmp"
    echo "  - pulls the latest code from git"
    echo "  - checks for and optionally runs pending DB migrations"
    echo "  - reloads the Flask app via mod_wsgi"
    echo ""
    echo "Rollback (code only):"
    echo "  rsync -a --delete /tmp/imagelib-<timestamp>/ $REPO/"
    echo "  touch $REPO/imagelib.wsgi"
    echo ""
    echo "Rollback (if a DB migration was also run):"
    echo "  cp $DB.<timestamp>.bak $DB"
    echo "  rsync -a --delete /tmp/imagelib-<timestamp>/ $REPO/"
    echo "  touch $REPO/imagelib.wsgi"
    exit 1
}

section() { echo ""; echo "==> $*"; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

if [ $# -gt 0 ]; then usage; fi

if [ "$(whoami)" != "nas" ]; then
    echo "ERROR: must run as the nas user."
    echo "       sudo -u nas $0"
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Back up current code
# ---------------------------------------------------------------------------

section "Backing up code"
BACKUP=/tmp/imagelib-$(date +%Y%m%d-%H%M%S)
cp -a "$REPO" "$BACKUP"
echo "    $BACKUP"

# ---------------------------------------------------------------------------
# 2. Handle any uncommitted local changes
# ---------------------------------------------------------------------------

cd "$REPO"

STASHED=0
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo ""
    echo "    Local changes detected:"
    git diff --stat
    git stash
    STASHED=1
    echo "    Stashed. Review later with: git stash show -p"
fi

# ---------------------------------------------------------------------------
# 3. Pull
# ---------------------------------------------------------------------------

section "Pulling"
git pull

if [ "$STASHED" -eq 1 ]; then
    echo ""
    echo "    NOTE: local changes were stashed and NOT reapplied."
    echo "    The pulled code should incorporate all prior production fixes."
    echo "    Review with: git stash show -p"
    echo "    Drop when satisfied: git stash drop"
fi

# ---------------------------------------------------------------------------
# 4. Check for pending schema migrations
# ---------------------------------------------------------------------------

section "Checking for pending migrations"

needs_migration() {
    # Returns 0 (true) if the named column is absent from the fits table
    python3 - "$DB" "$1" <<'EOF'
import sqlite3, sys
db_path, col = sys.argv[1], sys.argv[2]
try:
    con = sqlite3.connect(db_path)
    cols = [r[1] for r in con.execute("PRAGMA table_info(fits)").fetchall()]
    con.close()
    sys.exit(0 if col not in cols else 1)
except Exception as e:
    print(f"    WARNING: could not read DB schema: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

PENDING=0
if needs_migration organization; then
    echo "    PENDING: update:orgproject"
    echo "             adds organization, project, observatory, observer columns"
    PENDING=1
fi

if [ "$PENDING" -eq 0 ]; then
    echo "    No migrations pending."
fi

if [ "$PENDING" -eq 1 ]; then
    echo ""
    printf "    Run pending migrations now? [y/N] "
    read -r answer
    if [[ "${answer,,}" == "y" ]]; then
        DB_BACKUP="$DB.$(date +%Y%m%d-%H%M%S).bak"
        echo "    Backing up DB to $DB_BACKUP"
        cp "$DB" "$DB_BACKUP"
        echo "    Running update:orgproject"
        echo "    (Answer 'y' at the prompt — DB is already backed up above)"
        python3 "$REPO/fitsdb.py" update:orgproject
    else
        echo "    Skipped. Run manually when ready:"
        echo "      python3 $REPO/fitsdb.py update:orgproject"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Reload Flask app via mod_wsgi
# ---------------------------------------------------------------------------

section "Reloading app"
touch "$REPO/imagelib.wsgi"
echo "    imagelib.wsgi touched — Apache/mod_wsgi will reload on next request"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

section "Done"
echo "    Code backup : $BACKUP"
echo "    Check logs  : tail /tmp/fitsfiles.out"

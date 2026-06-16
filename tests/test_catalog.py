"""Unit tests for catalog.py"""
import pytest
import catalog


def _insert_entry(db, object_name, other='', cname=None):
    """Insert one catalog entry and its aliases into the test DB."""
    if cname is None:
        cname = object_name
    cur = db.con.cursor()
    cur.execute(
        "INSERT INTO catalog (object, other, type, con) VALUES (?,?,?,?)",
        [object_name, other, 'Gx', 'UMa'],
    )
    row_id = cur.lastrowid
    cur.execute(
        "INSERT INTO catalog_by_target (target, id, cname) VALUES (?,?,?)",
        [object_name, row_id, cname],
    )
    for alt in other.split(';'):
        alt = alt.strip()
        if alt:
            cur.execute(
                "INSERT INTO catalog_by_target (target, id, cname) VALUES (?,?,?)",
                [alt, row_id, cname],
            )
    db.con.commit()


# ---------------------------------------------------------------------------
# prettyspace (pure function, no DB needed)
# ---------------------------------------------------------------------------

def test_prettyspace_strips_leading_trailing_spaces():
    assert catalog.Catalog.prettyspace('  M 51  ') == 'M 51'


def test_prettyspace_strips_quotes():
    assert catalog.Catalog.prettyspace('"NGC 5194"') == 'NGC 5194'


def test_prettyspace_collapses_internal_spaces():
    assert catalog.Catalog.prettyspace('M  51') == 'M 51'


def test_prettyspace_mixed():
    assert catalog.Catalog.prettyspace(' "  NGC  5194 " ') == 'NGC 5194'


# ---------------------------------------------------------------------------
# cname (requires DB with catalog schema)
# ---------------------------------------------------------------------------

def test_cname_found(fresh_catalog_db):
    _insert_entry(fresh_catalog_db, 'NGC 5194', other='M 51', cname='M 51')
    assert catalog.Catalog.cname('NGC 5194') == 'M 51'


def test_cname_alias_lookup(fresh_catalog_db):
    _insert_entry(fresh_catalog_db, 'NGC 5194', other='M 51', cname='M 51')
    assert catalog.Catalog.cname('M 51') == 'M 51'


def test_cname_not_found_returns_input(fresh_catalog_db):
    assert catalog.Catalog.cname('Unknown Blob') == 'Unknown Blob'


def test_cname_messier_preferred_over_ngc(fresh_catalog_db):
    """When both NGC and Messier names exist, cname should return the Messier one."""
    _insert_entry(fresh_catalog_db, 'NGC 5194', other='M 51', cname='M 51')
    assert catalog.Catalog.cname('NGC 5194') == 'M 51'
    assert catalog.Catalog.cname('M 51') == 'M 51'


def test_cname_lazy_db_init(fresh_catalog_db, monkeypatch):
    """Catalog.db must be None at fixture start and initialised on first call."""
    # fresh_catalog_db fixture already set Catalog.db = None via monkeypatch
    assert catalog.Catalog.db is None
    catalog.Catalog.cname('anything')
    assert catalog.Catalog.db is not None


def test_malformed_catalog_line_skipped(tmp_path, monkeypatch):
    """The next→continue fix: a line with too few fields is skipped, not inserted."""
    import fitsdb
    import subprocess
    import sys

    db_path = str(tmp_path / 'cat.db')
    monkeypatch.setattr(fitsdb.Fitsdb, 'dbfile', db_path)
    db = fitsdb.Fitsdb()

    # Build a minimal catalog file: 5-column header, one good line, one short line
    cat_file = tmp_path / 'test.cat'
    cat_file.write_text(
        '"object","other","type","con","mag"\n'
        '"NGC 5194","M 51","Gx","CVn","8.6"\n'
        '"MALFORMED"\n'           # too few fields — must be skipped
        '"NGC 5457","M 101","Gx","UMa","7.9"\n'
    )

    result = subprocess.run(
        [sys.executable, 'catalog.py', 'create', str(cat_file)],
        capture_output=True, text=True,
    )
    # Process must succeed (exit 0)
    assert result.returncode == 0
    # Both valid entries inserted, malformed one skipped
    assert '2 catalog entries added' in result.stdout
    assert 'Not enough fields' in result.stdout

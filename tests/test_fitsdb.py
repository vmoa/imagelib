"""Unit tests for fitsdb.py"""
import pytest


def _rec(**overrides):
    base = dict(
        target='M 51', object='NGC 5194', date='2024-06-01',
        timestamp='2024-06-01T04:30:00.000', filter='Clear',
        binning='2x2', exposure=300.0, x=200, y=100,
        path='/test/img.fits', preview='/test/img.png',
        thumbnail='/test/img-thumb.png', imagetype='tgt',
    )
    base.update(overrides)
    return base


def test_insert_returns_one(fresh_db):
    assert fresh_db.insert(_rec()) == 1


def test_duplicate_path_rejected(fresh_db):
    fresh_db.insert(_rec())
    assert fresh_db.insert(_rec()) == 0


def test_different_paths_both_inserted(fresh_db):
    assert fresh_db.insert(_rec(path='/test/a.fits')) == 1
    assert fresh_db.insert(_rec(path='/test/b.fits')) == 1


def test_inserted_data_readable(fresh_db):
    fresh_db.insert(_rec(target='NGC 5194', filter='Ha', exposure=600.0))
    cur = fresh_db.con.cursor()
    row = cur.execute(
        "SELECT target, filter, exposure FROM fits WHERE path = ?",
        ['/test/img.fits'],
    ).fetchone()
    assert row == ('NGC 5194', 'Ha', 600.0)


def test_cal_imagetype_stored(fresh_db):
    fresh_db.insert(_rec(imagetype='cal', target='Dark Frame 120s'))
    cur = fresh_db.con.cursor()
    row = cur.execute(
        "SELECT imagetype FROM fits WHERE path = ?", ['/test/img.fits']
    ).fetchone()
    assert row[0] == 'cal'


def test_status_query(fresh_db):
    fresh_db.insert(_rec(path='/test/a.fits', date='2024-06-01'))
    fresh_db.insert(_rec(path='/test/b.fits', date='2024-06-02'))
    cur = fresh_db.con.cursor()
    total = cur.execute("SELECT count(*) FROM fits").fetchone()[0]
    assert total == 2

#
# catalog.py -- catalog manipulation routines
#   Saguaro Astronomy Club Database version 8.1
#   https://www.saguaroastro.org/sac-downloads/
#

import argparse
import datetime
import os
import re
import sqlite3
import sys

import fitsdb

# Original thoughts on CNAME
#               (1) the Messier number (based on finding `object` in the SAC catalog)
#               (2) the SAC catalog `object`
#               (3) a meta-image-type name (eg: dark, bias, light, etc)
#               (4) whatever is in the fits `object` field'''

class Catalog:

    re_left   = re.compile('^[ "]+')   # Leading space or quote
    re_right  = re.compile('[ "]+$')   # Trailing space or quote
    re_center = re.compile(' +')       # Multispace sequences

    re_messier = re.compile('^M \d+$')

    catalog = {
        'sag': {
            'table': 'sag_catalog',
            'columns': [ 'object', 'other', 'type', 'con', 'ra', 'dec', 'mag', 'subr', 'u2k', 'ti', 'size_max', 'size_min', 'pa',
                         'class', 'nsts', 'brstr', 'bchm', 'ngc_descr', 'notes'],
            'qmarks': [],
            'defname': 0,
            'othernames': [ 1 ]
        },
        'iau': {
            'table': 'iau_catalog',
            'columns': [ 'name', 'disignation', 'bayer', 'con', 'wds_j', 'mag', 'bnd', 'hip', 'hd', 'ra', 'dec', 'date', 'notes' ],
            'qmarks': [],
            'defname': 0,
            'othernames': [ 1 ]
        },
        'cat': {
            'table': 'catalog',
            'columns' = [ 'taget TEXT', 'cname TEXT', 'table TEXT', 'id INTEGER' ],
            'qmarks': [],
            'defname': None,
            'othernames': [ None ]
        }
    } &&&&&
    sag_qmarks  = [ '?' ] * length(sag_columns)
    iau_qmarks  = [ '?' ] * length(iau_columns)
    cat_qmarks  = [ '?' ] * length(cat_columns)

    db = fitsdb.Fitsdb()

    def init(self):
        ### print(">>> Connecting to database")
        self.db = fitsdb.Fitsdb()

    @classmethod
    def prettyspace(cls, string):
        string = re.sub(cls.re_left, '', string)
        string = re.sub(cls.re_right, '', string)
        string = re.sub(cls.re_center, ' ', string)
        return(string)

    @classmethod
    def cname(cls, object):
        '''Return the canonical name for `object`.'''
        ### print(">>> cname({})".format(object))
        if (not cls.db):
            cls.__init__()
        cur = cls.db.con.cursor()
        sql = "select cname from catalog_by_target where target = ?"
        ### print(">>> {} WITH {}".format(sql, object)) ###DEBUG
        row = cur.execute(sql, [ object ]).fetchone()
        if (row):
            return(row[0])
        else:
            return(object)

    @classmethod
    def divine(cls, fn):
        '''Divine catalog type of `fn`.'''
        if (sys.file.exists(fn)):
            if (regex.match('DeepSky', fn)):
                return('deepsky')
            elsif (regext.match('star', fn)):
                return('star')
            else:
                print("Cannot divine file type for {}".format(fn))
                sys.exit(1)
        else:
            print("File not found: {}".format(fn))
            sys.exit(1)



#
# Non-class admin methods (or should they be part of class?)
#


def check_catalog_files(args):
    '''Confirm input files exist before dropping tables.'''
    missing_file = 0
    for fn in args:
        if (not os.path.exists(fn)):
            print("{}: file not found".format(fn))
            missing_file += 1
    if (missing_file):
        sys.exit(1)
    return


def drop_tables(cur):
    '''Drop catalog tables.'''
    missing_table = 0
    for table in [ sag_catalog, iau_catalog, catalog_by_target ]:
        sql = "DROP TABLE {}".format(table)
        ### print(">>> {}".format(sql))
        try:
            cur.execute(sql)
            db.con.commit()
            print("Table {} dropped".format(table))
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            if (er.args[0][0:14] == 'no such table:'):
                missing_table = 1
    if (missing_table):
        print('You meant maybe `create` instead?')
        sys.exit(1)


def create_tables(cur):
    '''Create catalog tables and indexes.'''
    # Create SAG catalog from (LINK)
    sql = "CREATE TABLE sag_catalog (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  {} TEXT\n)".format(' TEXT,\n  '.join(Catalog.sag_columns))
    print(">>> {}".format(sql))
    try:
        cur.execute(sql)
        cur.execute("CREATE UNIQUE INDEX sqg_catalog_object_index ON catalog (object)")
        cur.execute("CREATE INDEX sqg_catalog_type_index ON catalog (type)")
        db.con.commit()
    except sqlite3.Error as er:
        print('ERROR: ' + ' '.join(er.args))
        if (er.args[0] == 'table sag_catalog already exists'):
            print("HINT: If you really want to recreate it, rerun using `recreate`")
        sys.exit(1)
    print("Table sag_catalog created")

    # Create IAU Named Stars catalog from https://www.iau.org/public/themes/naming_stars/
    # by way of https://github.com/mirandadam/iau-starnames.git
    sql = "CREATE TABLE iau_catalog (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  {} TEXT\n)".format(' TEXT,\n  '.join(Catalog.iau_columns))
    print(">>> {}".format(sql))
    try:
        cur.execute(sql)
        cur.execute("CREATE UNIQUE INDEX iau_catalog_bayer_index ON iau_catalog (bayer)")
        cur.execute("CREATE UNIQUE INDEX iau_catalog_hip_index ON iau_catalog (hip)")
        db.con.commit()
    except sqlite3.Error as er:
        print('ERROR: ' + ' '.join(er.args))
        if (er.args[0] == 'table iau_catalog already exists'):
            print("HINT: If you really want to recreate it, rerun using `recreate`")
        sys.exit(1)
    print("Table iau_catalog created")

    # Create master catalog with several entries referencing specific catalogs
    sql = "CREATE TABLE catalog (\n  {}\n)".format(',\n  '.join(Catalog.cat_columns))
    print(">>> {}".format(sql))
    try:
        cur.execute(sql)
        cur.execute("CREATE INDEX catalog_by_target_target_index ON catalog_by_target (target)")
        cur.execute("CREATE INDEX catalog_by_target_table_id_index ON catalog_by_target (table, id)")
        db.con.commit()
    except sqlite3.Error as er:
        print('ERROR: ' + ' '.join(er.args))
        if (er.args[0] == 'table catalog already exists'):
            print("HINT: If you really want to recreate it, rerun using `recreate`")
        sys.exit(1)
    print("Table catalog_by_target created")


def populate_table(cur, table, sac_catalog):
    '''Read SAC data file and insert into table.'''
    print("Populating SAG catalog from {}".format(sag_catalog))
    file = open(sag_catalog)

    # Read and validate headerline
    headerline = file.readline()
    if (md5(headerline) != Catalog.sac_md5):
        print("Uh oh, {} has changed! (found {} expected {})".format(sag_catalog, md5(headerline), Catalog.sac_md5))
        sys.exit(1)

    linenum = 1  # We already processed header
    insertCount = 0
    aliasCount = 0
    datalines = file.readlines()
    for dataline in datalines:
        linenum += 1

        # Twiddle the data
        ### print(">>> dataline: {}".format(dataline))
        data = list()
        for d in dataline.rstrip().split('","'):
            data.append(cat.prettyspace(d))
        ### print(">>> data: {}".format(data))
        if (len(data) != len(Catalog.sag_header)):
            print("Not enough fields at line {}; skipping (found {} expected {})".format(linenum, len(data), len(header)))
            next

        # Insert into SAG catalog
        sql = 'INSERT INTO sag_catalog ({}) VALUES ({})'.format(','.join(Catalog.sag_header), ','.join(Catalog.sag_qmarks))
        ### print(">>> {}".format(sql))
        try:
            cur.execute(sql, data)
            # db.con.commit()
            id = cur.lastrowid
            insertCount += 1
        except sqlite3.Error as er:
            if (er.args[0] == 'UNIQUE constraint failed: catalog.object'):
                print("Duplicate {} entry found at line {}; skipping".format(data[0], linenum))
                insertCount -= 1
            else:
                print('ERROR: ' + ' '.join(er.args))
                sys.exit(1)

        # Get all our possible names
        targets = [ data[0] ]           # [0] is object
        for alt in data[1].split(';'):  # [1] is `other` name(s) for object
            targets.append(alt)

        # Figure out canonical name
        cname = data[0]                 # default to `object`
        for target in targets:
            if (cat.re_messier.match(target)):
                cname = target          # override with Messier
                break

        # Add all our names to lookup table
        for target in targets:
            if (target):
                sql = "insert into catalog (target, cname, table, id) values (?,?,?,?)"
                ### print(">>> {} {}".format(sql, [ target, cname, 'sag_catalog', id ]))
                cur.execute(sql, [ target, cname, 'sag_catalog', id ])
                aliasCount += 1

        db.con.commit()
        print("{} catalog entries added".format(insertCount))
        print("{} target aliases added".format(aliasCount))
        db.con.close()


#
# Admin interface
#

if (__name__ == "__main__"):

    catalogs = [ 'deepsky', 'star' ]

    # Rolling my own; argparse() just wasn't doing it...
    prog = os.path.basename(__file__)
    usage = '''Usage: {} cmd [--options] [arguments]
        {} create catalog_file      Creates and populates the catalog from `catalog_file`
        {} recreate catalog_file    Drops existing catalog and recreates (see `create`)
        {} stats                    Prints some statistics about the catalog
        {} query [field] term       Looks up `term` in catalog `field` (default: target)
                                            Fields may be target | type (default: target)'''.format(prog,prog,prog,prog,prog)

    # prog [re]create /path/to/SAC_DeepSky_VerXX_QCQ.TXT /path/to/'IAU star names - Official IAU Catalog.csv'

    cmd = None
    args = [ None ]
    if (len(sys.argv) >= 2):
        cmd = sys.argv[1]
    if (len(sys.argv) >= 3):
        args = sys.argv[2:]
    ### print(">>> cmd: {}".format(cmd))

    cat = Catalog()
    db = fitsdb.Fitsdb()

    if (cmd == 'create' or cmd == 'recreate'):

        if (len(args) != 2):
            print("Need to specify both SAC and IAU catalogs (probably SAC_DeepSky_VerXX_QCQ.TXT and IAU-CSN.json)")
            print($usage)
            exit(1)

        cur = db.con.cursor()
        if (cmd == 'recreate'):
            check_catalog_files(args)
            drop_tables(cur)

        create_tables(cur)
        populate_sac_table(cur, args[0])
        populate_iau_table(cur, args[1])
        sys.exit()

    elif (cmd == 'stats'):
        cur = db.con.cursor()
        total_rows = cur.execute("select count(*) from catalog").fetchone()[0]
        total_aliases = cur.execute("select count(*) from catalog_by_target").fetchone()[0]

        type = dict()
        sql = 'select type, count(type) from catalog group by 1 order by 2 desc'
        for row in cur.execute(sql).fetchall():
            type[row[0]] = row[1]

        con = dict()
        sql = 'select con, count(con) from catalog group by 1 order by 2 desc'
        for row in cur.execute(sql).fetchall():
            con[row[0]] = row[1]

        print("The catalog contains {:,} objects with {:,} aliases".format(total_rows, total_aliases))
        print("\nThere are {} types of objects:".format(len(type)))
        x = 0
        for t,v in type.items():
            x += 1
            print("{:-5d} {:10s}".format(v,t), end='')
            if (x >= 8):
                print("")
                x = 0
        print("")

        print("\nAll {} constellations are represented:".format(len(con)))
        x = 0
        for c,v in con.items():
            x += 1
            print("{:-5d} {:10s}".format(v,c), end='')
            if (x >= 8):
                print("")
                x = 0
        print("")

        sys.exit(0)

    elif (cmd == 'query'):
        print("Wuery not yet implemented.")
        #  object TEXT,
        #  other TEXT,
        #  type TEXT,
        #  con TEXT,

    else:
        if (cmd):
            print("{}: unknown command".format(cmd))
        print(usage)
        sys.exit(1)

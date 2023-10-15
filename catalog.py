#
# catalog.py -- catalog manipulation routines
#
# Saguaro Astronomy Club Database version 8.1
# https://www.saguaroastro.org/sac-downloads/
#
# IAU Named Stars catalog from https://www.iau.org/public/themes/naming_stars/
# by way of https://github.com/mirandadam/iau-starnames.git
#

import argparse
import csv
import datetime
import hashlib
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
    re_whitespace = re.compile(r'\s+')
    re_mcg_match = re.compile(r'^MCG(\d)')


    catalog = {
        'sac': {
            'table':   'sac_catalog',
            'columns': [ 'object', 'other', 'type', 'con', 'ra', 'dec', 'mag', 'subr', 'u2k', 'ti', 'size_max', 'size_min', 'pa',
                         'class', 'nsts', 'brstr', 'bchm', 'ngc_descr', 'notes'],
            'indices': [ 'UNIQUE:object', ':type' ],
            'names':   [ 'object', 'other' ],
            'qmarks':  [],
            'md5':     'ba5a59bfcf97d6aa588404ad4b479694',
        },
        'iau': {    # ,IAU Name ,Designation,HIP,Bayer Name,#,WDS_J,Vmag,RA(J2000),Dec(J2000),Origin,Etymology Note,Source,,ID,Const.
            'table':   'iau_catalog',
            'columns': [ 'name', 'designation', 'hip', 'bayer', 'num', 'wds_j', 'mag', 'ra', 'dec', 'origin', 'note', 'source', 'unused', 'cid', 'con' ],
            'indices': [ 'UNIQUE:name', ':hip', ':bayer' ],
            'names':   [ 'name', 'designation', 'hip', 'bayer' ],
            'qmarks':  [],
            'md5':     '18836c4bd7c694568f0d830f5e38e409',
        },
        'cat': {
            'table':   'catalog',
            'columns': [ 'target', 'cname', 'table_name', 'table_id' ],
            'indices': [ ':cname', 'UNIQUE:target', ':table_name,table_id' ],
            'names':   [],
            'qmarks':  [],
            'md5':     0,
        }
    } 
    catalog['sac']['qmarks']  = [ '?' ] * len(catalog['sac']['columns'])
    catalog['iau']['qmarks']  = [ '?' ] * len(catalog['iau']['columns'])
    catalog['cat']['qmarks']  = [ '?' ] * len(catalog['cat']['columns'])

    db = fitsdb.Fitsdb()

    def init(self):
        pass

    @classmethod
    def prettyspace(cls, string):
        string = string.replace('"', '')
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
        sql = "select cname from catalog where target = ?"
        ### print(">>> {} WITH {}".format(sql, object)) ###DEBUG
        row = cur.execute(sql, [ object ]).fetchone()
        if (row):
            return(row[0])
        else:
            return(object)

    @classmethod
    def divine(cls, file, fn):
        '''Read header from file and return catalog type.'''
        headerline = file.readline()
        header_md5 = hashlib.md5(headerline.encode('utf-8')).hexdigest()
        for type in Catalog.catalog.keys():
            if (header_md5 == Catalog.catalog[type]['md5']):
                return(type)
        print("Cannot divine catalog type for {}. (md5:{})".format(fn, header_md5))
        return(None)


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
    for cattype in Catalog.catalog.keys():
        table = Catalog.catalog[cattype]['table']
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
        #sys.exit(1)


def create_tables(cur):
    '''Create catalog tables and indexes.'''
    for cattype in Catalog.catalog.keys():
        cat = Catalog.catalog[cattype]
        table = Catalog.catalog[cattype]['table']
        columns = Catalog.catalog[cattype]['columns']
        
        sql = "CREATE TABLE {} (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  {} TEXT\n)".format(table, ' TEXT,\n  '.join(columns))
        try:
            ### print(">>> " + sql)
            cur.execute(sql)
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            if (er.args[0].find('already exists') >= 0):
                print("HINT: If you really want to recreate it, rerun using `recreate`")
            #sys.exit(1)

        count = 0
        for index in Catalog.catalog[cattype]['indices']:
            (unique, col) = index.split(':')
            sql = "CREATE {} INDEX {}_index{} on {} ({})".format(unique, table, count, table, col)
            ### print(">>> " + sql)
            cur.execute(sql) 
            count += 1

        db.con.commit()
        print("Table {} created".format(table))


def populate_table(cur, fn):
    '''Read `fn`, divine type, and insert into appropriate table.'''
    print("Divining catalog type of {}".format(fn))
    file = open(fn)
    cattype = Catalog.divine(file, fn)
    if (cattype):
        cat = Catalog.catalog[cattype]
    else:
        return

    print("Populating {} catalog from {}".format(cattype, fn))
    sql1 = 'INSERT INTO {} ({}) VALUES ({})'.format(cat['table'], ','.join(cat['columns']), ','.join(cat['qmarks']))
    colcount = len(cat['columns'])

    linenum = 1  # We already processed header in `divine()`
    insertCount = 0
    for data in csv.reader(file):
        linenum += 1

        # Twiddle the data
        data = [ Catalog.prettyspace(d) for d in data ]
        if (cattype == 'iau'):
            data = data[1:]     # First column is null
            if (data[2]):       # Prefix HIP for easy searching
                data[2] = 'HIP ' + data[2]
            if (data[4] and data[4] != '-' and data[4] != '_'):  # Full Bayer designation, eg α Cen B
                data[3] = data[3] +' '+ data[4]
        #print(">>> data: {}".format(data))
        if (len(data) != colcount):
            print("Wrong number of fields at line {}; skipping (found {} expected {})".format(linenum, len(data), colcount))
            continue

        # Insert into catalog
        try:
            #print(">>> {} {}".format(sql1, data))
            cur.execute(sql1, data)
            id = cur.lastrowid
            insertCount += 1
        except sqlite3.Error as er:
            if (er.args[0].find('UNIQUE constraint failed') >= 0):
                print("Duplicate {} entry found at line {}; skipping".format(data[0], linenum))
            else:
                print('ERROR: ' + ' '.join(er.args))
                sys.exit(1)

    db.con.commit()
    print("{} {} catalog entries added".format(insertCount, cattype))



def build_master_catalog(cur):
    '''Pull the records from all xxx_catalogs and build the master catalog.'''
    print('Building master catalog')
    aliasCount = 0
    for cattype in Catalog.catalog.keys():
        if (cattype == 'cat'):  # This is the one we're building!
            continue

        print(">>> Processing {} --> catalog".format(cattype))
        table = Catalog.catalog[cattype]['table']
        columns = Catalog.catalog[cattype]['names']

        # Build a dict of alternate names from catalog keyed by cname
        targets = dict()
        id = dict()
        select = "select id, {} from {} order by id".format(', '.join(columns), table)
        ### print(">>> " + select)
        for row in cur.execute(select).fetchall():
            theseTargets = cleanupTargets(row[1:])
            cname = theseTargets[0]
            targets[cname] = theseTargets[1:]
            id[cname] = row[0]

        # First iterate over targets and record cnames so they win the UNIQUE constraint
        for cname in targets.keys():
            aliasCount += insertMasterRow(cname, cname, table, id[cname])

        # Then re-iterate over targets and record alternate names
        for cname in targets.keys():
            for target in targets[cname]:
                aliasCount += insertMasterRow(target, cname, table, id[cname])

    db.con.commit()
    print("{} target aliases added".format(aliasCount))

def cleanupTargets(row):
    '''Split out and clean up target names. First target is cname.'''
    targets = list()
    for cell in row:
        for target in cell.split(';'):
            if (target.find('_') == 0 or target.find('-') == 0):  # Skip Bayer desingation with ascii mapping challenge
                continue
            if (target.find('MCG') == 0):   # SAC catalog MCG names are afu -- see https://heasarc.gsfc.nasa.gov/W3Browse/galaxy-catalog/mcg.html
                target = re.sub(Catalog.re_whitespace, '', target)          # Strip all whitespace
                target = re.sub(Catalog.re_mcg_match, r'MGC-\1', target)    # And fix intermittently missing hyphen
            targets.append(target)
            if (Catalog.re_messier.match(target)):      # If Messier, swap with targets[0] so it's the cname
                targets[len(targets)-1] = targets[0]
                targets[0] = target
    return(targets)

def insertMasterRow(target, cname, table, id):
    '''Insert row into master catalog.'''
    if (not target):
        return(0)
    sql2 = "insert into catalog (target, cname, table_name, table_id) values (?,?,?,?)"
    try:
        ### print(">>> {} {}".format(sql2, [ target, cname, table, id ]))
        cur.execute(sql2, [ target, cname, table, id ])
        return(1)
    except sqlite3.Error as er:
        if (er.args[0].find('UNIQUE constraint failed') >= 0):
            print("Duplicate canonical name for {} found {}; skipping".format(cname, [ target, cname, table, id ]))
            return(0)
        else:
            print('ERROR: ' + ' '.join(er.args))
            sys.exit(1)


#
# Admin interface
#

if (__name__ == "__main__"):

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
            print(usage)
            exit(1)

        cur = db.con.cursor()
        if (cmd == 'recreate'):
            check_catalog_files(args)
            drop_tables(cur)

        create_tables(cur)
        populate_table(cur, args[0])
        populate_table(cur, args[1])
        build_master_catalog(cur)
        db.con.close()
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

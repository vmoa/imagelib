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


if (__name__ == "__main__"):

    # Rolling my own; argparse() just wasn't doing it...
    prog = os.path.basename(__file__)
    usage = '''Usage: {} cmd [--options] [arguments]
        {} create catalog_file      Creates and populates the catalog from `catalog_file`
        {} recreate catalog_file    Drops existing catalog and recreates (see `create`)
        {} stats                    Prints some statistics about the catalog
        {} query [field] term       Looks up `term` in catalog `field` (default: target)
                                            Fields may be target | type (default: target)'''.format(prog,prog,prog,prog,prog)

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

        catalogfile = args[0]
        if (not catalogfile):
            print("Catalog filename needed for creation. (This is probably SAC_DeepSky_VerXX_QCQ.TXT.)")
            print(usage)
            sys.exit(1)

        file = open(catalogfile)
        cur = db.con.cursor()

        if (cmd == 'recreate'):
            error = None
            for table in [ 'catalog', 'catalog_by_target' ]:
                sql = "DROP TABLE {}".format(table)
                ### print(">>> {}".format(sql))
                try:
                    cur.execute(sql)
                    db.con.commit()
                    print("Table {} dropped".format(table))
                except sqlite3.Error as er:
                    print('ERROR: ' + ' '.join(er.args))
                    if (er.args[0][0:14] == 'no such table:'):
                        error = 1
            if (error):
                print('You meant maybe `create` instead?')
                sys.exit(1)

        # Parse header into a list (and build our qmarks)
        headerline = file.readline().rstrip().replace('"','').lower()
        header = list()
        qmarks = list()
        for hdr in headerline.split(','):
            header.append(cat.prettyspace(hdr).replace(' ','_'))  # boo!
            qmarks.append('?')
        ### print(">>> headerline: {}$".format(headerline))
        ### print(">>> header: ({}) {}".format(len(header), header))
        ### print(">>> qmarks: ({}) {}".format(len(qmarks), qmarks))

        # Build sql CREATE statement based on columns called out in headerfile
        # Note that `object`, `other` and `type` have to exist or Bad Things will happen
        cols = list()
        cols.append('id INTEGER PRIMARY KEY AUTOINCREMENT')
        for hdr in header:
            cols.append('{} TEXT'.format(hdr))
        sql = 'CREATE TABLE catalog ({}\n)'.format(',\n  '.join(cols))
        ### print(">>> {}".format(sql))

        # Intentionally fail if table exists
        try:
            cur.execute(sql)
            cur.execute("CREATE UNIQUE INDEX catalog_object_index ON catalog (object)")
            cur.execute("CREATE INDEX catalog_type_index ON catalog (type)")
            cur.execute("CREATE TABLE catalog_by_target ( target TEXT, id INTEGER, cname TEXT )")
            cur.execute("CREATE INDEX catalog_by_target_target_index ON catalog_by_target (target)")
            cur.execute("CREATE INDEX catalog_by_target_id_index ON catalog_by_target (id)")
            db.con.commit()
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            if (er.args[0] == 'table catalog already exists'):
                print("HINT: If you really want to recreate it, rerun using `recreate`")
            sys.exit(1)

        print("Tables catalog, catalog_by_target created")

        # Insert data
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
            if (len(data) != len(header)):
                print("Not enough fields at line {}; skipping (found {} expected {})".format(linenum, len(data), len(header)))
                next

            # Insert into catalog
            sql = 'INSERT INTO catalog ({}) VALUES ({})'.format(','.join(header), ','.join(qmarks))
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
                    sql = "insert into catalog_by_target (target, id, cname) values (?,?,?)"
                    ### print(">>> {} {}".format(sql, [ target, id, cname ]))
                    cur.execute(sql, [ target, id, cname ])
                    aliasCount += 1

        db.con.commit()
        print("{} catalog entries added".format(insertCount))
        print("{} target aliases added".format(aliasCount))
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

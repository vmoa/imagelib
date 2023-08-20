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

class Catalog:

    pass

    re_left   = re.compile('^[ "]+')   # Leading space or quote
    re_right  = re.compile('[ "]+$')   # Trailing space or quote
    re_center = re.compile(' +')       # Multispace sequences

    @classmethod
    def prettyspace(cls, string):
        string = re.sub(cls.re_left, '', string)
        string = re.sub(cls.re_right, '', string)
        string = re.sub(cls.re_center, ' ', string)
        return(string)

    
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
    print(">>> cmd: {}".format(cmd))

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
            cur.execute("CREATE TABLE catalog_by_target ( target TEXT, id INTEGER )")
            cur.execute("CREATE INDEX catalog_by_target_target_index ON catalog_by_target (target)")
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

            # Add lookup data
            targets = [ data[0] ]           # [0] is object
            for alt in data[1].split(';'):  # [1] is `other` name(s) for object
                targets.append(alt)
            for target in targets:
                if (target):
                    sql = "insert into catalog_by_target (target, id) values (?,?)"
                    print(">>> {} {}".format(sql, [ target, id ]))
                    cur.execute(sql, [ target, id ])
                    aliasCount += 1

        db.con.commit()
        print("{} catalog entries added".format(insertCount))
        print("{} target aliases added".format(aliasCount))
        db.con.close()
        sys.exit()

    elif (cmd == 'stats'):
        print("Stats not yet implemented.")

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

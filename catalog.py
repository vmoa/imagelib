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

    parser = argparse.ArgumentParser(description='Catalog utilities.')
    parser.add_argument('--create', '-C', dest='create', action='store_true', help='create the catalog table and import form `--file`')
    parser.add_argument('--recreate', dest='recreate', action='store_true', help='drop exisint catalog and then recreate (see `--create`')
    parser.add_argument('--import', '-I', dest='import', action='store_true', help='import catalog data')
    parser.add_argument('--stats', '-s', dest='stats', action='store_true', help='print catalog statistics')
    parser.add_argument('--query', '-q', dest='query', action='store', help='look up a catalog entry')
    parser.add_argument('--file', '-f', dest='catalogfile', action='store', help='catalog input file')
    args = parser.parse_args()
    ### print(">>> args: {}".format(vars(args)))

    cat = Catalog()
    db = fitsdb.Fitsdb()

    if ('create' in vars(args) or 'recreate' in vars(args)): # args.create or args.recreate):

        if (not 'catalogfile' in vars(args)):
            print("Catalog filename needed for creation. (This is probably SAC_DeepSky_VerXX_QCQ.TXT.)")
            sys.exit(1)

        file = open(args.catalogfile)
        cur = db.con.cursor()

        if ('recreate' in vars(args)):
            sql = 'DROP TABLE catalog'
            ### print(">>> {}".format(sql))
            try:
                cur.execute(sql)
                db.con.commit()
            except:
                print('ERROR: ' + ' '.join(er.args))
                #if (er.args[0] == 'table catalog already exists'):
                #    print("HINT: If you really want to recreate it, run `sqlite3 fits.db` and enter:\n  drop table catalog;")
                sys.exit(1)
            print("Table catalog dropped")

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
            db.con.commit()
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            if (er.args[0] == 'table catalog already exists'):
                print("HINT: If you really want to recreate it, rerun using `--recreate`")
            sys.exit(1)

        print("Table catalog created")

        # Insert data
        linenum = 1  # We already processed header
        insert = 0
        datalines = file.readlines()
        for dataline in datalines:
            linenum += 1
            ### print(">>> dataline: {}".format(dataline))
            data = list()
            for d in dataline.rstrip().split('","'):
                data.append(cat.prettyspace(d))
            ### print(">>> data: {}".format(data))
            if (len(data) != len(header)):
                print("Not enough fields at line {}; skipping (found {} expected {})".format(linenum, len(data), len(header)))
                next

            sql = 'INSERT INTO catalog ({}) VALUES ({})'.format(','.join(header), ','.join(qmarks))
            ### print(">>> {}".format(sql))
            try:
                cur.execute(sql, data)
                insert += 1
            except sqlite3.Error as er:
                if (er.args[0] == 'UNIQUE constraint failed: catalog.object'):
                    print("Duplicate {} entry found at line {}; skipping".format(data[0], linenum))
                    insert -= 1
                else:
                    print('ERROR: ' + ' '.join(er.args))
                    sys.exit(1)

        db.con.commit()
        print("{} catalog entries added".format(insert))
        db.con.close()
        sys.exit()

    elif (args.stats):
        print("Stats not yet implemented.")

    elif (args.query):
        print("Wuery not yet implemented.")

    else:
        print("What do you want to do?")

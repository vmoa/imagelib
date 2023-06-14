#
# Database routeines using SQLite database
#

import sys
import sqlite3

class Fitsdb:

    dbfile = 'fits.db'   # Should probably have a full path one day

    def __init__(self):
        self.con = sqlite3.connect(self.dbfile)
        self.cur = self.con.cursor()

    def __del__(self):
        self.con.close()

    def execute_and_commit(self, sql):
        self.cur.execute(sql)
        self.con.commit()

    def insert(self, image):
        cols = list()
        vals = list()
        qmarks = list()
        for c,v in image.items():
            cols.append(c)
            vals.append(v)
            qmarks.append('?')

        questionmarks = ', '.join(qmarks)

        sql = 'insert into fits ({}) values ({})'.format(', '.join(cols), questionmarks)
        print(sql, "\n>> ", vals, "\n")
        self.cur.execute(sql, vals)
        self.con.commit()

# Stand-alone adminy stuff
if (__name__ == "__main__"):

    db = Fitsdb()

    command = None
    if (len(sys.argv) > 1):
        command = sys.argv[1]

    if (command == 'create'):

    # Intentionally fail if table exists
        db.cur.execute('''
            CREATE TABLE fits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fndate TEXT,
                filter TEXT,
                binning TEXT,
                exposure TEXT,
                target TEXT,
                altname TEXT,
                date TEXT,
                path TEXT,
                preveiw TEXT,
                thumbnail TEXT
            )
        ''')

        db.cur.execute("CREATE UNIQUE INDEX fits_path_index ON fits (path)")
        db.cur.execute("CREATE INDEX fits_date_name_index ON fits (date, target)")
        db.cur.execute("CREATE INDEX fits_name_date_index ON fits (target, date)")
        db.con.commit()

    if (command == 'status'):
        print("Yeah, sorry... not implemented yet")

    db.con.close()

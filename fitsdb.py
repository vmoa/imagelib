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
        for c,v in image:
            cols.append(c)
            vals.append(v)

        for x in vals:
            questionmarks += '?,'
        questionmarks = questionmarks[:-1]  # drop the trailing comma

        sql = 'insert into fits ( {} ) values ( {} )'.format(','.join(cols), questionmarks)
        self.cur.executemany(sql, vals)

# Stand-alone adminy stuff
if (__name__ == "__main__"):

    db = Fitsdb()

    command = None
    if (len(sys.argv) > 1):
        command = sys.argv[1]

    if (command == 'create'):

        db.cur.execute('''
            CREATE TABLE fits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fndate TEXT,
                filter TEXT,
                binning TEXT,
                exposure TEXT,
                target TEXT,
                date TEXT,
                path TEXT,
                preveiw TEXT,
                thumbnail TEXT
            )
        ''')

        db.cur.execute("CREATE INDEX fits-date-name ON fits (date, target)")
        db.cur.execute("CREATE INDEX fits-name-date ON fits (target, date)")
        db.con.commit()

    if (command == 'status'):
        print("Yeah, sorry... not implemented yet")

    db.con.close()

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
        '''Insert image (dictionary) into the database.'''
        cols = list()
        vals = list()
        qmarks = list()
        for c,v in image.items():
            cols.append(c)
            vals.append(v)
            qmarks.append('?')

        questionmarks = ', '.join(qmarks)

        sql = 'insert into fits ({}) values ({})'.format(', '.join(cols), questionmarks)
        try:
            self.cur.execute(sql, vals)
            self.con.commit()
        except sqlite3.Error as er:
            print('WARNING: ' + ' '.join(er.args))
            return(0)

        return(1)


# Stand-alone adminy stuff
if (__name__ == "__main__"):

    db = Fitsdb()

    command = None
    if (len(sys.argv) > 1):
        command = sys.argv[1]

    if (command == 'create'):

        # Intentionally fail if table exists
        try:
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
                    preview TEXT,
                    thumbnail TEXT
                )
            ''')
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            sys.exit(1)

        db.cur.execute("CREATE UNIQUE INDEX fits_path_index ON fits (path)")
        db.cur.execute("CREATE INDEX fits_date_name_index ON fits (date, target)")
        db.cur.execute("CREATE INDEX fits_name_date_index ON fits (target, date)")
        db.con.commit()
        db.con.close()
        sys.exit()

    if (command == 'status' or command == 'stat'):
        total_rows = db.cur.execute("select count(*) from fits").fetchone()[0]
        targets = db.cur.execute("select distinct(target), count(*) from fits GROUP by target order by 2 desc, 1 asc").fetchall()
        dates = db.cur.execute("select distinct(date), count(*) from fits GROUP by date order by 2 desc, 1 asc").fetchall()
        db.con.close()

        print("Database Status:\n  Total images: {}".format(total_rows))

        t = list()
        for row in targets:
            t.append("{}({})".format(row[0], row[1]))
        print("  Targets: {} --> {}".format(len(targets), ', '.join(t)))

        t = list()
        for row in dates:
            t.append("{}({})".format(row[0], row[1]))
        print("  Dates: {} --> {}".format(len(dates), ', '.join(t)))
        sys.exit()

    if (command):
        print("Unknown command: {}".format(command))
    else:
        print("Usage: fitsdb.py create|status")

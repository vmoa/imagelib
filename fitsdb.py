#
# Database routeines using SQLite database
#

import os
import re
import sys
import sqlite3

class Fitsdb:

    if (os.path.exists('/home/nas/data')):
        dbfile = '/home/nas/data/fits.db'
        tsfile = '/home/nas/data/fits.last_run'
    else:
        dbfile = 'fits.db'
        tsfile = 'fits.last_run'


    def __init__(self):
        # All threads use a single connection, so care must be taken when writing!
        self.con = sqlite3.connect(self.dbfile, check_same_thread=False)

    def __del__(self):
        self.con.close()

    def execute_and_commit(self, sql):
        cur = self.con.cursor()
        cur.execute(sql)
        self.con.commit()

    def insert(self, image):
        '''Insert image (dictionary) into the database.'''
        #print(">>> fitsdb.insert(): imagetype: {}".format(image['imagetype']))   # DEBUG
        cols = list()
        vals = list()
        qmarks = list()
        for c,v in image.items():
            cols.append(c)
            vals.append(v)
            qmarks.append('?')

        questionmarks = ', '.join(qmarks)

        cur = self.con.cursor()
        sql = 'insert into fits ({}) values ({})'.format(', '.join(cols), questionmarks)
        # print(">>> {} WITH {}".format(sql, vals)) ###DEBUG
        try:
            cur.execute(sql, vals)
            self.con.commit()
        except sqlite3.Error as er:
            print('WARNING: ' + ' '.join(er.args))
            return(0)

        return(1)



# Stand-alone adminy stuff
if (__name__ == "__main__"):

    db = Fitsdb()
    Commands = list()  # for syntax report

    command = None
    if (len(sys.argv) > 1):
        command = sys.argv[1]

    Commands.append('create')
    if (command == 'create'):

        # Intentionally fail if table exists
        # Most fields are FITS header fields, or based on them, excpet:
        #   `target` is a derived field; either calibration frame or catalog.cname()
        #   `path` is the filesystem path to the fits file
        #   `preview` is the filesystem path to the full scale png preview file
        #   `thumbnail` is the filesystem path to the scaled thumbnail png file
        #   `imagetypee` is type of image, either "Calibration" or "Target"
        cur = db.con.cursor()
        try:
            cur.execute('''
                CREATE TABLE fits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT,
                    object TEXT,
                    date TEXT,
                    timestamp TEXT,
                    filter TEXT,
                    binning TEXT,
                    exposure REAL,
                    x INTEGER,
                    y INTEGER,
                    path TEXT,
                    preview TEXT,
                    thumbnail TEXT,
                    imagetype TEXT
                )
            ''')
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            sys.exit(1)

        cur.execute("CREATE UNIQUE INDEX fits_path_index ON fits (path)")
        cur.execute("CREATE INDEX fits_date_name_index ON fits (date, target)")
        cur.execute("CREATE INDEX fits_name_date_index ON fits (target, date)")
        db.con.commit()

        try:
            cur.execute('''
                CREATE TABLE fits_by_target (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT,
                    date TEXT,
                    fits_id INTEGER,
                    FOREIGN KEY(fits_id) REFERENCES fits(id)
                )
            ''')
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            sys.exit(1)

        cur.execute("CREATE INDEX fits_by_target_target ON fits_by_target (target)")
        cur.execute("CREATE INDEX fits_by_target_target_date ON fits_by_target (target, date)")
        db.con.commit()

        db.con.close()
        sys.exit()

    Commands.append('status')
    if (command == 'status' or command == 'stat'):
        cur = db.con.cursor()
        total_rows = cur.execute("select count(*) from fits").fetchone()[0]
        targets = cur.execute("select distinct(target), count(*) from fits GROUP by target order by 2 desc, 1 asc").fetchall()
        dates = cur.execute("select distinct(date), count(*) from fits GROUP by date order by 2 desc, 1 asc").fetchall()
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

    Commands.append('update:imagetype')
    if (command == 'update:imagetype'):
        # Add the `imagetype` column and then populate it
        cur = db.con.cursor()

        print("Updating the database to add `imagetype`; have you backed up fits.db? ", end='')
        if (input()[0].lower() != 'y'):
            exit(1)

        # This will (should?) fail with 'duplicate column name' if column already exists
        sql = 'ALTER TABLE fits ADD COLUMN imagetype TEXT'
        print(">>> {}".format(sql))
        try:
            cur.execute(sql)
        except sqlite3.Error as er:
            print('ERROR: ' + ' '.join(er.args))
            sys.exit(1)

        # Now walk all rows and collect id's of Calibration and Target frames
        cal_ids = list()
        tgt_ids = list()
        cal_re = re.compile('(Flat|Bias|Dark) Frame')
        sql = 'SELECT id, target FROM fits ORDER BY id'
        print(">>> {}".format(sql))
        for (id,target) in (cur.execute(sql).fetchall()):
            if (cal_re.match(target)):
                cal_ids.append(id)
            else:
                tgt_ids.append(id)

        # Update calibration imagetype
        sql = "update fits set imagetype = 'Calibration' where id in ( {} )".format(','.join(str(x) for x in cal_ids))
        print(">>> {}".format(sql))
        cur.execute(sql)

        # Update target imagetype
        sql = "update fits set imagetype = 'Target' where id in ( {} )".format(','.join(str(x) for x in tgt_ids))
        print(">>> {}".format(sql))
        cur.execute(sql)

        db.con.commit()
        db.con.close()
        sys.exit()


    if (command):
        print("Unknown command: {}".format(command))
    else:
        print("Usage: fitsdb.py {}".format(' | '.join(Commands)))

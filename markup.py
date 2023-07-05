#
# markup.py -- django markup routines
#

import flask
import json
import os
import re
import sys
import time
import zipfile

import fitsdb

class Markup:

    db = fitsdb.Fitsdb()
    thumb_max = 64    # Number of thumbnails to display (rounded up to fill the grouping)
    sequence = 0      # To prevent download file collisions

    def __init__(self):
        pass

    def build_images(self, start=None):
        '''Build a template (dictionary) of which images to display.'''
        dates = list()
        cur = self.db.con.cursor()
        if (start):
            rows = cur.execute("select distinct(date) from fits where date <= ? order by date desc", (start,)).fetchall()
        else:
            rows = cur.execute("select distinct(date) from fits order by date desc").fetchall()
        for row in rows:
            dates.append(row[0])

        images = dict()
        images["title"] = "RFO Image Library: All"
        images["collections"] = list()

        thumb_count = 0
        for date in dates:

            if (thumb_count >= self.thumb_max):
                images["next"] = date
                break

            collection = dict()
            prefix = "rfo_{}".format(date)
            collection["id"] = prefix
            collection["prefix"] = prefix
            collection["title"] = date
            collection["pics"] = list()

            sequence = 0
            rows = cur.execute("select id, target, thumbnail, preview from fits where date = '{}' order by id".format(date)).fetchall()
            for row in rows:
                thumb_count += 1
                sequence += 1
                recid, target, thumbnail, preview = row
                if (thumbnail[0:15] == '/home/nas/Eagle'):
                    thumbnail = thumbnail[10:]
                pic = dict()
                pic["id"] = "{}_{:03d}".format(prefix, sequence)
                pic["recid"] = recid
                pic["title"] = target
                pic["src"] = thumbnail
                pic["preview"] = preview  # Not used cuz I couln't figure out how to sneak it in
                collection["pics"].append(pic)

            images["collections"].append(collection)

        # print(json.dumps(images, indent=4))
        return(images)

    def zipit(self, recidstr):
        '''Query the database for specified record IDs, zip up the fits files and return zip file path.'''
        recids = recidstr.split(',')
        qmarks = list()
        for x in recids:
            qmarks.append('?')
        questionmarks = ', '.join(qmarks)

        cur = self.db.con.cursor()
        sql = "select id, path from fits where id in ({}) order by id".format(questionmarks)
        rows = cur.execute(sql, recids)

        # Experiments show that at compressionlevel=1, the zip file is 3% larger than at =9, but 9 takes 5 times as long
        self.sequence += 1
        datestr = time.strftime('%Y-%m-%d')
        tempfn = '/tmp/fits_{}_{:04d}.zip'.format(datestr, self.sequence)
        if (os.path.exists(tempfn)):
            os.remove(tempfn)
        with zipfile.ZipFile(tempfn, mode='x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zip:
            for row in rows:
                id, path = row
                zip.write(path, arcname=os.path.basename(path))

        return(tempfn)


if (__name__ == "__main__"):

    app = flask.Flask(__name__)
    markup = Markup()
    t = markup.build_images()
    with app.app_context():
        print(flask.render_template('imagelib.html', **t))

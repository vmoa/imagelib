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

    def build_images(self, start=None, target=None):
        '''Build a template (dictionary) of which images to display.'''
        print("build_images(start={}, target={})".format(start,target))
        targets = list()
        cur = self.db.con.cursor()
        rows = cur.execute("select distinct(target) from fits order by target").fetchall()
        for row in rows:
            targets.append(row[0])

        # Recreate a list of dates, restricted by target if specified
        dates = list()
        cur = self.db.con.cursor()
        if (target):
            rows = cur.execute("select distinct(date) from fits where target = '{}' order by date desc".format(target)).fetchall()
        else:
            rows = cur.execute("select distinct(date) from fits order by date desc").fetchall()
        for row in rows:
            dates.append(row[0])

        images = dict()
        images["title"] = "RFO Image Library: {}".format(target if target else 'All')
        if (target):
            images["target"] = target
        images["allTargets"] = targets
        images["obsDates"] = dates
        images["collections"] = list()

        # Figure out where to start if from Prev or Next
        startX = dates.index(start) if (start) else 0
        if (startX > 0):
            images["prev"] = dates[startX - 1]

        thumb_count = 0
        for date in dates[startX:]:

            if (thumb_count >= self.thumb_max):
                images["next"] = date
                break

            if (target):
                rows = cur.execute("select id, target, thumbnail, preview from fits where date = '{}' and target = '{}' order by id".format(date,target)).fetchall()
            else:
                rows = cur.execute("select id, target, thumbnail, preview from fits where date = '{}' order by id".format(date)).fetchall()

            collection = dict()
            prefix = "rfo_{}".format(date)
            collection["id"] = prefix
            collection["prefix"] = prefix
            if (target):
                collection["title"] = "{}: {}".format(target, date)
            else:
                collection["title"] = date
            collection["pics"] = list()

            sequence = 0
            for row in rows:
                thumb_count += 1
                sequence += 1
                recid, thisTarget, thumbnail, preview = row
                if (thumbnail[0:15] == '/home/nas/Eagle'):
                    thumbnail = thumbnail[10:]
                pic = dict()
                pic["id"] = "{}_{:03d}".format(prefix, sequence)
                pic["recid"] = recid
                pic["title"] = thisTarget
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

    def fetchDeets(self, recid):
        '''Return formatted HTML of the FITS details for `recid`.'''
        tags = ( 'target', 'timestamp', 'filter', 'binning', 'exposure', 'x', 'y' )
        cur = self.db.con.cursor()
        sql = "select {} from fits where id = ?".format(', '.join(tags))
        # print(">>> {} WITH {}".format(sql, recid))  ###DEBUG
        rows = cur.execute(sql, (recid,))

        deets = '<p><b><u>FITS Details:</u></b></br>\n'
        for row in rows:
            x = 0
            for tag in tags:
                deets += "<b>{}:</b> {}</br>\n".format(tag, row[x])
                x += 1
        deets += '</p>'
        return(deets)


if (__name__ == "__main__"):

    app = flask.Flask(__name__)
    markup = Markup()
    t = markup.build_images()
    with app.app_context():
        print(flask.render_template('imagelib.html', **t))

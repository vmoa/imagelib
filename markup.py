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

    def fetchTargets(self, target=None):
        '''Return list of distinct targets that match, handling empty target and fuzzy matches.'''
        cur = self.db.con.cursor()
        targets = list()

        if (not target):
            # All targets
            cur.execute("select distinct(target) from fits order by target")
        else:
            # Start with an exact match (case sensitive)
            cur.execute("select distinct(target) from fits where target = ? order by target", [target])
            if (cur.rowcount == 0):
                # If nothing returned, do a fuzzy match (case insenstive)
                cur.execute("select distinct(target) from fits where target like ? order by target", [ '%'+target+'%' ])

        for row in cur.fetchall():
            targets.append(row[0])
        return(targets)

    def fetchDates(self, target=None):
        '''Return list of distinct dates for this target, handling empty target and fuzzy matches.'''
        cur = self.db.con.cursor()
        dates = list()

        if (not target):
            # All dates
            cur.execute("select distinct(date) from fits order by date desc")
        else:
            # Start with an exact match (case sensitive)
            cur.execute("select distinct(date) from fits where target = ? order by date desc", [target])
            if (cur.rowcount == 0):
                # If nothing returned, do a fuzzy match (case insenstive)
                cur.execute("select distinct(date) from fits where target like ? order by date desc", [ '%'+target+'%' ])

        for row in cur.fetchall():
            dates.append(row[0])
        return(dates)

    def findStartDate(self, dates, start):
        '''Return index of dates closest to start.'''
        startX = 0
        if (start):
            for date in dates:
                if (date <= start):
                    break
                startX += 1
        if (startX >= len(dates)):
            print(">>> start date {} not found".format(start))
            startX = 0
        print(">>> startX: {}".format(startX))
        return(startX)

    def fetchDetails(self, cur, target=None, date=None):
        '''Return list of details (tuple) that match target and date.'''
        cur = self.db.con.cursor()
        details = list()

        if (not target):
            cur.execute("select id, target, thumbnail, preview from fits where date = ? order by id", [ date ])
        else:
            cur.execute("select id, target, thumbnail, preview from fits where target = ? and date = ? order by id", [ target, date ])
            if (cur.rowcount == 0):
                cur.execute("select id, target, thumbnail, preview from fits where target like ? and date = ? order by id", [ '%'+target+'%', date ])

        for row in cur.fetchall():
            details.append(row)
        return(details)


    def build_images(self, start=None, target=None, lastTarget=None):
        '''Build a template (dictionary) of which images to display.'''
        print(">>> build_images(start={}, target={})".format(start,target))

        images = dict()
        images['title'] = "RFO Image Library: {}".format(target if target else 'All')
        images['allTargets'] = self.fetchTargets()

        targets = self.fetchTargets(target)
        if (len(targets) == 0):
            # Flash an error and refetch lastTarget
            flask.flash("Target '{}' not found".format(target))
            target = lastTarget
            targets = self.fetchTargets(target)
        if (target):
            images['target'] = target

        # Reset date if new target chosen
        if (lastTarget != target):
            start = None

        dates = self.fetchDates(target)
        startX = self.findStartDate(dates, start)
        if (start):
            images['date'] = dates[startX]
        if (startX > 0):
            images['prev'] = dates[startX - 1]
        images['obsDates'] = dates

        print(">>> dates: {}".format(dates))
        print(">>> start: {}".format(start))

        thumb_count = 0
        images["collections"] = list()
        for date in dates[startX:]:

            if (thumb_count >= self.thumb_max):
                images["next"] = date
                break

            # Build a collection for each date
            collection = dict()
            prefix = "rfo_{}".format(date)
            collection["id"] = prefix
            collection["prefix"] = prefix
            if (target):
                collection["title"] = "{}: {}".format(target, date)
            else:
                collection["title"] = date
            collection["pics"] = list()

            # Fetch pic details for this date
            sequence = 0
            rows = self.fetchDetails(target, date)
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

        for thang in [ 'target', 'date', 'start', 'prev', 'next' ]:
            if (thang in images):
                print(">>> images[{}]: {}".format(thang, images[thang]))

        # print(json.dumps(images, indent=4))
        return(images)

    def zipit(self, recidstr):
        '''Query the database for specified record IDs, zip up the fits files and return zip file path.'''
        print(">>> zipit({})".format(recidstr))
        recids = recidstr.split(',')
        qmarks = list()
        for x in recids:
            qmarks.append('?')
        questionmarks = ', '.join(qmarks)

        cur = self.db.con.cursor()
        sql = "select id, path from fits where id in ({}) order by id".format(questionmarks)
        print(">>> {} [{}]".format(sql,recids))
        rows = cur.execute(sql, recids)
        print(">>> returned {} rows".format(rows.rowcount))

        # Experiments show that at compressionlevel=1, the zip file is 3% larger than at =9, but 9 takes 5 times as long
        self.sequence += 1
        datestr = time.strftime('%Y-%m-%d')
        tempfn = '/tmp/fits_{}_{:04d}.zip'.format(datestr, self.sequence)
        if (os.path.exists(tempfn)):
            os.remove(tempfn)
        with zipfile.ZipFile(tempfn, mode='x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zip:
            for row in rows:
                print(">>> adding {}".format(row))
                id, path = row
                zip.write(path, arcname=os.path.basename(path))
        zip.close()
        print(">>> return({})".format(tempfn))
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

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

    thumb_max = 64    # Number of thumbnails to display (rounded up to fill the grouping)
    sequence = 0      # To prevent download file collisions

    def __init__(self):
        self.db = fitsdb.Fitsdb()
        version_fn = 'VERSION' if os.path.exists('VERSION') else '/home/nas/flask/imagelib/VERSION'
        with open(version_fn, 'r') as vfile:
            self.version = vfile.readline().strip()
        print(">>> Markup version {}; connected to {}".format(self.version, self.db))
        print(">>> Working directory: {}".format(os.getcwd()))

    def reset(self):
        '''Reset lists each time we're called.'''
        print('>>> markup.reset()')
        self.where_list = list()  # Where clause
        self.what_list = list()   # Human description for page title

        # Collect some stats
        cur = self.db.con.cursor()
        self.total_rows = cur.execute("select count(*) from fits").fetchone()[0]
        self.total_cals = cur.execute("select count(*) from fits where imagetype = 'cal'").fetchone()[0]
        self.total_tgts = cur.execute("select count(*) from fits where imagetype = 'tgt'").fetchone()[0]
        self.distinct_tgts = cur.execute("select count(distinct(target)) from fits where imagetype = 'tgt'").fetchone()[0]

    def add_where(self, w):
        self.where_list.append(w)

    def get_where(self):
        return(' AND '.join(self.where_list))

    def add_what(self, w):
        self.what_list.append(w)

    def get_what(self):
        return(' '.join(self.what_list))

    def buildWhere_imgfilter(self, imgfilter):
        '''Upeate where clause to restrict by imgfilter if either cal or tgt selected. (Both doesn't require a where clause.)'''
        if (imgfilter == 'cal'):
            self.add_where('imagetype = "cal"')
            self.add_what('Calibration:')
        elif (imgfilter == 'tgt'):
            self.add_where('imagetype = "tgt"')
            self.add_what('Target:')

    def buildWhere_target(self, target):
        '''Update where cluse to match target if exact match, else do a fuzzy lookup.'''
        if (target):
            cur = self.db.con.cursor()
            sql = "select count(*) from fits where target = ?"
            if (self.where_list):
                sql += " and {}".format(self.get_where())
            if (cur.execute(sql, [ target ]).fetchone()[0] > 0):
                self.add_where('target = "{}"'.format(target))  # Query above untaints target
                self.add_what(target)
            else:
                self.add_where('target like "%{}%"'.format(target))
                self.add_what('matching <{}>'.format(target))

        if (not self.what_list):
                self.add_what('ALL')

    def fetchTargets(self, target=None):
        '''Return list of distinct targets that match, handling empty target and fuzzy matches.'''
        sql = "SELECT DISTINCT(target) FROM fits"
        if (self.where_list):
            sql += " WHERE {}".format(self.get_where())
        sql += ' ORDER BY target'

        print(">>> {}".format(sql))    ### DEBUG
        cur = self.db.con.cursor()
        cur.execute(sql)
        targets = list()
        for row in cur.fetchall():
            targets.append(row[0])
        print(">>> fetchTargets({}) ==> {} rows".format(target, len(targets)))
        return(targets)

    def fetchDates(self, target=None):
        '''Return list of distinct dates for this target, handling empty target and fuzzy matches.'''
        sql = "SELECT DISTINCT(date) FROM fits"
        if (self.where_list):
            sql += " WHERE {}".format(self.get_where())
        sql += " ORDER BY date DESC"

        print(">>> {}".format(sql))    ### DEBUG
        cur = self.db.con.cursor()
        cur.execute(sql)
        dates = list()
        for row in cur.fetchall():
            dates.append(row[0])
        print(">>> fetchDates({}) ==> {} rows".format(target, len(dates)))
        return(dates)

    def fetchDetails(self, target=None, date=None):
        '''Return list of details (tuple) that match target and date.'''
        cur = self.db.con.cursor()
        sql = "SELECT id, target, thumbnail, preview FROM fits"
        if (self.where_list):
            sql += " WHERE {}".format(self.get_where())
            sql += " AND date = ?"
        else:
            sql += " WHERE date = ?"
        sql += " ORDER BY id"

        print(">>> {} with ({})".format(sql,date))    ### DEBUG
        cur = self.db.con.cursor()
        cur.execute(sql, [date])
        details = list()
        for row in cur.fetchall():
            details.append(row)
        print(">>> fetchDetails(t:{}, d:{}) ==> {} rows".format(target, date, len(details)))
        return(details)

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
        print(">>> findStartDate({}) ==> {}".format([len(dates), start], startX))
        return(startX)

    def noneify(self, var):
        '''Make it easy to compare None to <emptystring>.'''
        if (not var):
            return('')
        else:
            return(var)


    # Main UI entrypoint
    def build_images(self, start=None, target=None, imgfilter='both', lastTarget=None):
        '''Build a template (dictionary) of which images to display.'''
        print(">>> build_images(start={}, target={}, imgfilter={}, lastTarget={})".format(start,target,imgfilter,lastTarget))
        self.reset()

        images = dict()
        self.buildWhere_imgfilter(imgfilter)
        images['version'] = self.version
        images['total_rows'] = self.total_rows
        images['total_cals'] = self.total_cals
        images['total_tgts'] = self.total_tgts
        images['distinct_tgts'] = self.distinct_tgts

        images['allTargets'] = self.fetchTargets(None)  # for autofill

        images['imgfilter'] = imgfilter
        images['imgfilter_checked'] = dict()
        for filter in [ 'cal', 'tgt', 'both' ]:
            images['imgfilter_checked'][filter] = 'checked' if filter == imgfilter else ''

        self.buildWhere_target(target)
        targets = self.fetchTargets(target)
        if (len(targets) == 0):
            # Flash an error and refetch lastTarget
            print(">>> target not found")
            flask.flash("Target '{}' not found".format(target))
            target = lastTarget
            targets = self.fetchTargets(target)
        if (target):
            images['target'] = target
            images['last_target'] = target

        # Reset date if new target chosen
        if (self.noneify(lastTarget) != self.noneify(target)):
            print(">>> lastTarget:{} != target:{} ==> start:None".format(lastTarget, target))
            images['start'] = ''
            start = None

        dates = self.fetchDates(target)
        startX = self.findStartDate(dates, start)
        if (start):
            images['date'] = dates[startX]
        if (startX > 0):
            images['prev'] = dates[startX - 1]
        images['obsDates'] = dates

        print(">>> dates: ({} of 'em)".format(len(dates)))
        print(">>> start: {}".format(start))
        images['title'] = "RFO Image Library: {}".format(self.get_what())  # set in searchType() as a side effect of any fetchXxx() call

        thumb_count = 0
        images['collections'] = list()
        for date in dates[startX:]:

            if (thumb_count >= self.thumb_max):
                images['next'] = date
                break

            # Build a collection for each date
            collection = dict()
            prefix = "rfo_{}".format(date)
            collection['id'] = prefix
            collection['prefix'] = prefix
            if (self.what_list):
                collection['title'] = "{}: {}".format(self.get_what(), date)
            else:
                collection['title'] = date
            collection['pics'] = list()

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
                pic['id'] = "{}_{:03d}".format(prefix, sequence)
                pic['recid'] = recid
                pic['title'] = thisTarget
                pic['src'] = thumbnail
                pic['preview'] = preview  # Not used cuz I couln't figure out how to sneak it in
                collection['pics'].append(pic)

            images['collections'].append(collection)

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

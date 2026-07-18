#
# markup.py -- django markup routines
#

import flask
import io
import logging
import json
import os
import re
import sys
import time
import zipfile

from astropy.io import fits as astrofits

import fitsdb

class Markup:

    thumb_max = 64    # Number of thumbnails to display (rounded up to fill the grouping)
    sequence = 0      # To prevent download file collisions

    def __init__(self):
        self.db = fitsdb.Fitsdb()
        version_fn = 'VERSION' if os.path.exists('VERSION') else '/home/nas/flask/imagelib/VERSION'
        with open(version_fn, 'r') as vfile:
            self.version = vfile.readline().strip()
        logging.info("Markup version {}; connected to {}".format(self.version, self.db))
        logging.info("Working directory: {}".format(os.getcwd()))

    def reset(self):
        '''Reset lists each time we're called.'''
        logging.debug("markup.reset()")
        self.where_list = list()  # List of (clause, params) tuples
        self.what_list = list()   # Human description for page title

        # Collect some stats
        cur = self.db.con.cursor()
        self.total_rows = cur.execute("select count(*) from fits").fetchone()[0]
        self.total_cals = cur.execute("select count(*) from fits where imagetype = 'cal'").fetchone()[0]
        self.total_tgts = cur.execute("select count(*) from fits where imagetype = 'tgt'").fetchone()[0]
        self.distinct_tgts = cur.execute("select count(distinct(target)) from fits where imagetype = 'tgt'").fetchone()[0]

    def add_where(self, clause, params=None):
        self.where_list.append((clause, params or []))

    def get_where(self):
        return ' AND '.join(clause for clause, _ in self.where_list)

    def get_params(self):
        result = []
        for _, params in self.where_list:
            result.extend(params)
        return result

    def add_what(self, w):
        self.what_list.append(w)

    def get_what(self):
        return(' '.join(self.what_list))

    def buildWhere_imgfilter(self, imgfilter):
        '''Update where clause to restrict by imgfilter if either cal or tgt selected. (Both doesn't require a where clause.)'''
        if (imgfilter == 'cal'):
            self.add_where('imagetype = ?', ['cal'])
            self.add_what('Calibration:')
        elif (imgfilter == 'tgt'):
            self.add_where('imagetype = ?', ['tgt'])
            self.add_what('Target:')

    def buildWhere_target(self, target):
        '''Update where clause to match target if exact match, else do a fuzzy lookup.'''
        if (target):
            cur = self.db.con.cursor()
            sql = "select count(*) from fits where target = ?"
            params = [target]
            if (self.where_list):
                sql += " and {}".format(self.get_where())
                params += self.get_params()
            if (cur.execute(sql, params).fetchone()[0] > 0):
                self.add_where('target = ?', [target])
                self.add_what(target)
            else:
                self.add_where('target like ?', ['%' + target + '%'])
                self.add_what('matching <{}>'.format(target))

        if (not self.what_list):
                self.add_what('ALL')

    def fetchTargets(self, target=None):
        '''Return list of distinct targets that match, handling empty target and fuzzy matches.'''
        sql = "SELECT DISTINCT(target) FROM fits"
        params = []
        if (self.where_list):
            sql += " WHERE {}".format(self.get_where())
            params = self.get_params()
        sql += ' ORDER BY target'

        logging.debug(">>> {}".format(sql))
        cur = self.db.con.cursor()
        cur.execute(sql, params)
        targets = list()
        for row in cur.fetchall():
            targets.append(row[0])
        logging.debug("fetchTargets({}) ==> {} rows".format(target, len(targets)))
        return(targets)

    def fetchDates(self, target=None):
        '''Return list of distinct dates for this target, handling empty target and fuzzy matches.'''
        sql = "SELECT DISTINCT(date) FROM fits"
        params = []
        if (self.where_list):
            sql += " WHERE {}".format(self.get_where())
            params = self.get_params()
        sql += " ORDER BY date DESC"

        logging.debug(">>> {}".format(sql))
        cur = self.db.con.cursor()
        cur.execute(sql, params)
        dates = list()
        for row in cur.fetchall():
            dates.append(row[0])
        logging.debug("fetchDates({}) ==> {} rows".format(target, len(dates)))
        return(dates)

    def fetchOrgProjects(self):
        '''Return list of distinct (organization, project) pairs where organization is set.'''
        cur = self.db.con.cursor()
        sql = "SELECT DISTINCT organization, project FROM fits WHERE organization IS NOT NULL ORDER BY organization, project"
        return cur.execute(sql).fetchall()

    def fetchObservatories(self):
        '''Return list of distinct observatory values.'''
        cur = self.db.con.cursor()
        sql = "SELECT DISTINCT observatory FROM fits WHERE observatory IS NOT NULL ORDER BY observatory"
        return [row[0] for row in cur.execute(sql).fetchall()]

    def fetchObservers(self):
        '''Return list of distinct observer values.'''
        cur = self.db.con.cursor()
        sql = "SELECT DISTINCT observer FROM fits WHERE observer IS NOT NULL ORDER BY observer"
        return [row[0] for row in cur.execute(sql).fetchall()]

    def buildWhere_orgproject(self, orgproject):
        '''Update where clause to filter by org|project combined value.'''
        if orgproject:
            parts = orgproject.split('|', 1)
            if len(parts) == 2:
                org, project = parts
                self.add_where('organization = ? AND project = ?', [org, project])
                self.add_what('{}|{}'.format(org, project))

    def buildWhere_observatory(self, observatory):
        '''Update where clause to filter by observatory.'''
        if observatory:
            self.add_where('observatory = ?', [observatory])
            self.add_what('observatory:{}'.format(observatory))

    def buildWhere_observer(self, observer):
        '''Update where clause to filter by observer.'''
        if observer:
            self.add_where('observer = ?', [observer])
            self.add_what('observer:{}'.format(observer))

    def fetchDetails(self, target=None, date=None):
        '''Return list of details (tuple) that match target and date.'''
        cur = self.db.con.cursor()
        sql = "SELECT id, target, thumbnail, preview, path FROM fits"
        params = []
        if (self.where_list):
            sql += " WHERE {}".format(self.get_where())
            sql += " AND date = ?"
            params = self.get_params() + [date]
        else:
            sql += " WHERE date = ?"
            params = [date]
        sql += " ORDER BY id"

        logging.debug(">>> {} with ({})".format(sql, date))
        cur = self.db.con.cursor()
        cur.execute(sql, params)
        details = list()
        for row in cur.fetchall():
            details.append(row)
        logging.debug("fetchDetails(t:{}, d:{}) ==> {} rows".format(target, date, len(details)))
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
            logging.warning("start date {} not found".format(start))
            startX = 0
        logging.debug("findStartDate({}) ==> {}".format([len(dates), start], startX))
        return(startX)

    def noneify(self, var):
        '''Make it easy to compare None to <emptystring>.'''
        if (not var):
            return('')
        else:
            return(var)


    # Main UI entrypoint
    def build_images(self, start=None, target=None, imgfilter='both', lastTarget=None,
                     orgproject=None, observatory=None, observer=None):
        '''Build a template (dictionary) of which images to display.'''
        logging.debug("build_images(start={}, target={}, imgfilter={}, lastTarget={})".format(start,target,imgfilter,lastTarget))
        self.reset()

        images = dict()
        self.buildWhere_imgfilter(imgfilter)
        images['version'] = self.version

        images['allTargets'] = self.fetchTargets(None)  # for autofill

        images['imgfilter'] = imgfilter
        images['imgfilter_checked'] = dict()
        for filter in [ 'cal', 'tgt', 'both' ]:
            images['imgfilter_checked'][filter] = 'checked' if filter == imgfilter else ''

        if orgproject:
            self.buildWhere_orgproject(orgproject)
        if observatory:
            self.buildWhere_observatory(observatory)
        if observer:
            self.buildWhere_observer(observer)

        self.buildWhere_target(target)

        # Compute stats filtered to the current search criteria
        _cur = self.db.con.cursor()
        _where = self.get_where()
        _params = self.get_params()
        if _where:
            images['total_rows'] = _cur.execute("SELECT COUNT(*) FROM fits WHERE {}".format(_where), _params).fetchone()[0]
            images['total_cals'] = _cur.execute("SELECT COUNT(*) FROM fits WHERE imagetype='cal' AND {}".format(_where), _params).fetchone()[0]
            images['total_tgts'] = _cur.execute("SELECT COUNT(*) FROM fits WHERE imagetype='tgt' AND {}".format(_where), _params).fetchone()[0]
            images['distinct_tgts'] = _cur.execute("SELECT COUNT(DISTINCT target) FROM fits WHERE imagetype='tgt' AND {}".format(_where), _params).fetchone()[0]
        else:
            images['total_rows'] = self.total_rows
            images['total_cals'] = self.total_cals
            images['total_tgts'] = self.total_tgts
            images['distinct_tgts'] = self.distinct_tgts

        targets = self.fetchTargets(target)
        if (len(targets) == 0):
            # Flash an error and refetch lastTarget
            logging.warning("target not found")
            flask.flash("Target '{}' not found".format(target))
            target = lastTarget
            targets = self.fetchTargets(target)
        if (target):
            images['target'] = target
            images['last_target'] = target

        # Reset date if new target chosen
        if (self.noneify(lastTarget) != self.noneify(target)):
            logging.debug("lastTarget:{} != target:{} ==> start:None".format(lastTarget, target))
            images['start'] = ''
            start = None

        dates = self.fetchDates(target)
        startX = self.findStartDate(dates, start)
        if (start):
            images['date'] = dates[startX]
        if (startX > 0):
            images['prev'] = dates[startX - 1]
        images['obsDates'] = dates

        logging.debug("dates: ({} of 'em)".format(len(dates)))
        logging.debug("start: {}".format(start))
        images['title'] = "RFO Image Library"

        thumb_count = 0
        has_compressed = False
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
                recid, thisTarget, thumbnail, preview, path = row
                if path and path.endswith('.fits.fz'):
                    has_compressed = True
                if (thumbnail[0:15] == '/home/nas/Eagle'):
                    thumbnail = thumbnail[10:]
                pic = dict()
                pic['id'] = "{}_{:03d}".format(prefix, sequence)
                pic['recid'] = recid
                pic['title'] = thisTarget
                pic['src'] = thumbnail
                collection['pics'].append(pic)

            images['collections'].append(collection)

        images['has_compressed'] = has_compressed
        images['orgProjects'] = self.fetchOrgProjects()
        images['observatories'] = self.fetchObservatories()
        images['observers'] = self.fetchObservers()
        images['orgproject'] = orgproject or ''
        images['observatory'] = observatory or ''
        images['observer'] = observer or ''

        for thang in [ 'target', 'date', 'start', 'prev', 'next' ]:
            if (thang in images):
                logging.debug("images[{}]: {}".format(thang, images[thang]))

        # print(json.dumps(images, indent=4))
        return(images)

    def zipit(self, recidstr, fmt='fz'):
        '''Query the database for specified record IDs, zip up the fits files and return zip file path.'''
        logging.debug("zipit({}, fmt={})".format(recidstr, fmt))
        recids = recidstr.split(',')
        qmarks = list()
        for x in recids:
            qmarks.append('?')
        questionmarks = ', '.join(qmarks)

        cur = self.db.con.cursor()
        sql = "select id, path from fits where id in ({}) order by id".format(questionmarks)
        logging.debug("{} [{}]".format(sql, recids))
        rows = cur.execute(sql, recids)
        logging.debug("returned {} rows".format(rows.rowcount))

        # Experiments show that at compressionlevel=1, the zip file is 3% larger than at =9, but 9 takes 5 times as long
        self.sequence += 1
        datestr = time.strftime('%Y-%m-%d')
        tempfn = '/tmp/fits_{}_{:04d}.zip'.format(datestr, self.sequence)
        if (os.path.exists(tempfn)):
            os.remove(tempfn)
        with zipfile.ZipFile(tempfn, mode='x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zip:
            for row in rows:
                logging.debug("adding {}".format(row))
                id, path = row
                if fmt == 'fits' and path.endswith('.fits.fz'):
                    with astrofits.open(path) as hdul:
                        buf = io.BytesIO()
                        hdul.writeto(buf)
                        buf.seek(0)
                        arcname = os.path.basename(path)[:-3]  # strip '.fz' → .fits
                        zip.writestr(arcname, buf.read())
                else:
                    zip.write(path, arcname=os.path.basename(path))
        logging.debug("return({})".format(tempfn))
        return(tempfn)

    def fetchDeets(self, recid):
        '''Return formatted HTML of the FITS details for `recid`.'''
        tags = ( 'target', 'timestamp', 'filter', 'binning', 'exposure', 'x', 'y' )
        cur = self.db.con.cursor()
        sql = "select {} from fits where id = ?".format(', '.join(tags))
        logging.debug(">>> {} WITH {}".format(sql, recid))
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

    if ((len(sys.argv) > 1) and (sys.argv[1] == '--debug')):
        logging.basicConfig(level=logging.DEBUG)
        logging.debug("Displaying diagnostic DEBUG drivel")
        del(sys.argv[1])

    app = flask.Flask(__name__)
    markup = Markup()
    t = markup.build_images()
    with app.app_context():
        print(flask.render_template('imagelib.html', **t))

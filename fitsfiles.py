#
# fitsfile.py -- file manipulation routines
#

import argparse
import datetime
import json
import os
import re
import sys

from astropy.io import fits

import catalog
import fitsdb

class FitsFiles:

    if (os.path.exists('/home/nas/Eagle')):
        fitspath = '/home/nas/Eagle'
    else:
        fitspath = 'Eagle'

    forcepng = False

    # Calibration Frame Map of FITS lower(`IMAGETYP`) --> `target` name
    CFrames = {
        'dark frame':   'Dark Frame',
        'dark field':   'Dark Frame',
        'dark':         'Dark Frame',
        'bias frame':   'Bias Frame',
        'bias field':   'Bias Frame',
        'bias':         'Bias Frame',
        'flat frame':   'Flat Frame',
        'flat field':   'Flat Frame',
        'flat':         'Flat Frame',
    }

    def __init__(self):
        pass

    # Precompile
    whitespace = re.compile(r'\s+')
    broken_iso = re.compile('\.\d\d$')

    def parseFitsHeader(self, filename):
        '''Parse the salient bits out of the FITS file header.'''
        with fits.open(filename) as fitsfile:
            # Find our first HDU with a 2-axis image (see https://docs.astropy.org/en/stable/io/fits/)
            i = 0
            for hdu in fitsfile:
                if (hdu.header['NAXIS'] == 2):
                    break
                i += 1

            headers = dict()
            for hdr in 'NAXIS1', 'NAXIS2', 'EXPTIME', 'IMAGETYP', 'XBINNING', 'YBINNING', 'OBJCTRA', 'OBJCTDEC', 'FILTER', 'OBJECT', 'DATE-OBS':
                if hdr in list(hdu.header.keys()):
                    headers[hdr] = hdu.header[hdr]

        # Clean up headers
        if ('OBJECT' in headers):
            headers['OBJECT'] = re.sub(self.whitespace, ' ', headers['OBJECT']).strip()
        if ('DATE-OBS' in headers):
            if (self.broken_iso.search(headers['DATE-OBS'])):
                headers['DATE-OBS'] += '0'  # Maixm reports hundreths of seconds (.xx); iso requires thousandths (.xxx)
        else:
            print("No DATE-OBS header in {}; skipping".format(filename))
            return(None)

        return(headers)

    def buildDatabaseRecord(self, filename, headers):
        '''Translate FITS headers into database record fields.'''
        record = dict()
        record['path'] = filename

        if ('OBJECT' in headers):
            record['object'] = headers['OBJECT']
        else:
            record['object'] = 'No Target'

        # Set `target` based on calibration frame or `cname` (defaults to `object`)
        ### print(">>> IMAGETYP: <{}>".format(headers['IMAGETYP'].lower()))
        if ('IMAGETYP' in headers and headers['IMAGETYP'].lower() in self.CFrames.keys()):
            record['target'] = "{} {}s".format(self.CFrames[headers['IMAGETYP'].lower()], int(headers['EXPTIME']))
            record['imagetype'] = 'cal'
        else:
            record['target'] = catalog.Catalog.cname(record['object'])
            record['imagetype'] = 'tgt'

        record['timestamp'] = headers['DATE-OBS']           # ISO 8601 (GMT) eg: 2023-05-20T05:41:18.042
        record['date'] = datetime.datetime.fromisoformat(headers['DATE-OBS']).strftime('%Y-%m-%d')  # YYYY-MM-DD (GMT) convenient for sorting
        if ('FILTER') in headers:
            record['filter'] = headers['FILTER'].strip()
        if ('XBINNING' in headers and 'YBINNING' in headers):
            record['binning'] = "{}x{}".format(headers['XBINNING'], headers['YBINNING'])
        if ('EXPTIME' in headers):
            record['exposure'] = headers['EXPTIME']
        if ('NAXIS1' in headers and 'NAXIS2' in headers):
            record['x'] = headers['NAXIS1']
            record['y'] = headers['NAXIS2']
        return(record)

    def fits2png(self, record):
        '''Generate and png preview and thumbnail images; return updated database record.'''
        preview = record['path'][:-5] + '.png'
        if (self.forcepng or not os.path.exists(preview)):
            cmd = 'fitspng -o \"{}\" \"{}\"'.format(preview, record['path'])
            os.system(cmd)
        record['preview'] = preview

        thumb = record['path'][:-5] + '-thumb.png'
        scaling = int(record['x'] / 128) + 1    # Reduce our image to get 128x? (or just slightly larger)
        if (self.forcepng or not os.path.exists(thumb)):
            cmd = 'fitspng -s {} -o \"{}\" \"{}\"'.format(scaling, thumb, record['path'])
            ### print(">>> {}".format(cmd))  ###DEBUG
            os.system(cmd)
        else:
            print("    Thumb already exists: {}".format(thumb))  ###DEBUG
        record['thumbnail'] = thumb

        return(record)

    def addFitsFile(self, filename):
        filename = filename.rstrip()
        if (not os.path.exists(filename)):
            print("Skipping {}: File not found!".format(filename))
            return(0)

        print("Importing {}".format(filename))   ###DEBUG
        headers = self.parseFitsHeader(filename)
        if (not headers):
            return(0)
        record = self.buildDatabaseRecord(filename, headers)
        #print(">>> addFitsFile: imagetype: {}".format(record['imagetype']))  # DEBUG
        record = self.fits2png(record)
        rowid = fitsdb.insert(record)
        if (rowid):
            return(1)
        else:
            return(0)

    def findNewFits(self, path, fitsdb, files):
        '''Find new FITS files since last time we were run.  Runs the `find` system command on `path` to locate *.fits newer than `ts_file`.'''

        if (files):
            # Skip all the find logic and just add files
            count = 0
            for filename in files:
                count += self.addFitsFile(filename)
            return(count)

        start_time = datetime.datetime.now()  # On the off chance new files come in during find
        newer_arg = '';
        if (os.path.exists(fitsdb.tsfile)):
            newer_arg = '-newer ' + fitsdb.tsfile
        find_cmd = "find {} {} -type f -a \( -name '*\.fits' -o -name '*\.fit' \)".format(path, newer_arg)
        ### print(">>> {}".format(find_cmd))   ###DEBUG

        count = 0
        with os.popen(find_cmd) as find_out:
            for filename in find_out:
                count += self.addFitsFile(filename)

        # Update the timestamp with our start time, but only if successful
        if (count > 0):
            timestamp = start_time.strftime("%Y%m%d%H%M.%S")  # [[CC]YY]MMDDhhmm[.ss] 
            cmd = "touch -t {} {}".format(timestamp, fitsdb.tsfile)
            os.system(cmd)

        return(count)


if (__name__ == "__main__"):

    parser = argparse.ArgumentParser(description='FITS file utilities.')
    parser.add_argument('--fitspath', '-f', dest='fitspath', action='store', help='path to fits files')
    parser.add_argument('--forcepng', '-p', dest='forcepng', action='store_true', help='force regeneration of PNG files even if they exist')
    parser.add_argument('file', nargs='*', help='full path to file to add (may be repeated)')
    args = parser.parse_args()

    fitsdb = fitsdb.Fitsdb()

    fitsfiles = FitsFiles()
    if (args.fitspath):
        fitsfiles.fitspath = args.fitspath
    if (args.forcepng):
        fitsfiles.forcepng = args.forcepng
    count = fitsfiles.findNewFits(fitsfiles.fitspath, fitsdb, files=args.file)

    print("Successfully added {} images".format(count))


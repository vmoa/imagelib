#
# fitsfile.py -- file manipulation routines
#

import argparse
import datetime
import json
import os
import re
import sys

import fitsdb


class FitsFiles:

    if (os.path.exists('/home/nas/Eagle/SkyX/Images')):
        fitspath = '/home/nas/Eagle/SkyX/Images'
    else:
        fitspath = 'Eagle'

    forcepng = False

    # Build this from file?
    ngc_catalog = {
        'NGC 1952': 'M1',
        'NGC 5457': 'M101',
    }

    def __init__(self):
        pass

    def parseFilename(self, filename):
        '''Parse `filename` and return a dictionary with the deets.'''
        image = {}
        name = []

        # First let's strip the .fits
        filename = os.path.splitext(filename)[0]
        fn_re = re.compile(' +')
        fn = fn_re.split(filename)

        # Work through filename components and see what matches
        # What doesn't match should be part of the target name
        for thang in fn:

            sequence_re = re.compile('^\d{8}')  # Catches 00000000NoAutoDark, which is probably broken anyway
            if (sequence_re.match(thang)):
                continue

            exposure_re = re.compile('^([\d\.]+)secs$')
            m = exposure_re.search(thang)
            if (m):
                image["exposure"] = m.group(0)
                continue

            binning_re = re.compile('^(\dx\d)$')
            m = binning_re.fullmatch(thang)
            if (m):
                image["binning"] = m.group(0)
                continue

            filter_re = re.compile('^(LUMEN|B|V|R|I|RED|GREEN|BLUE|HA)$')
            m = filter_re.fullmatch(thang)
            if (m):
                image["filter"] = m.group(0)
                continue

            datestr_re = re.compile('^(\d{4}-\d{2}-\d{2})$')
            m = datestr_re.fullmatch(thang)
            if (m):
                image["fndate"] = m.group(0)
                continue

            # Anything left becomes target name
            name.append(thang)

        # Now assemble the name
        target = ' '.join(name)
        if (target in self.ngc_catalog):
            image["target"] = self.ngc_catalog[target]
            image["altname"] = target
        else:
            image["target"] = target

        return(image)

    def fits2png(self, image):
        '''Generate png preview and thumbnail images.'''
        # scaling is how much to reduce our image to get a 128x? thumbnail (or just slightly larger)
        if ('binning' in image):
            if (image['binning'] == '4x4'):
                scaling = 8
            elif (image['binning'] == '3x3'):
                scaling = 11
            elif (image['binning'] == '2x2'):
                scaling = 17
            elif (image['binning'] == '1x1'):
                scaling = 35
            else:
                scaling = 35
        else:
            scaling = 35

        preview = image["path"][:-5] + '.png'
        if (self.forcepng or not os.path.exists(preview)):
            cmd = 'fitspng -o \"{}\" \"{}\"'.format(preview, image["path"])
            os.system(cmd)

        thumb = image["path"][:-5] + '-thumb.png'
        if (self.forcepng or not os.path.exists(thumb)):
            cmd = 'fitspng -s {} -o \"{}\" \"{}\"'.format(scaling, thumb, image["path"])
            os.system(cmd)

        return(preview, thumb)

    def findNewFits(self, path, fitsdb):
        '''Find new FITS files since last time we were run.  Runs the `find` system command on `path` to
           locate *.fits newer than `ts_file`.
           TBD: Stash the results in a list and build indexes into the list.'''
        if (os.path.exists(fitsdb.tsfile)):
            newer_arg = '-newer ' + fitsdb.tsfile
        else:
            newer_arg = '';

        start_time = datetime.datetime.now()  # On the off chance new files come in during find
        count = 0

        find_cmd = "find {} {} -name '*\.fits'".format(path, newer_arg)
        with os.popen(find_cmd) as find_out:
            for fullpath in find_out:
                fullpath = fullpath.rstrip()
                path = fullpath.split('/')
                filename = path.pop()
                datestr = path.pop()

                # We're only interested in folders that are dates
                datestr_re = re.compile("(\d{4}-\d{2}-\d{2})");
                m = datestr_re.search(datestr)
                if (m):
                    image = self.parseFilename(filename)
                    image["date"] = m.group(0)
                    image["path"] = fullpath
                    (p,t) = self.fits2png(image)
                    image['preview'] = p
                    image['thumbnail'] = t
                    count += fitsdb.insert(image)

        # Update the timestamp with our start time, but only if successful
        if (count > 0):
            timestamp = start_time.strftime("%Y%m%d%H%M.%S")  # [[CC]YY]MMDDhhmm[.ss] 
            cmd = "touch -t {} {}".format(timestamp, fitsdb.tsfile)
            print(cmd)
            os.system(cmd)

        return(count)


if (__name__ == "__main__"):

    parser = argparse.ArgumentParser(description='FITS file utilities.')
    parser.add_argument('--fitspath', '-f', dest='fitspath', action='store', help='path to fits files')
    parser.add_argument('--forcepng', '-p', dest='forcepng', action='store_true', help='force regeneration of PNG files even if they exist')
    args = parser.parse_args()

    fitsdb = fitsdb.Fitsdb()

    fitsfiles = FitsFiles()
    if (args.fitspath):
        fitsfiles.fitspath = args.fitspath
    if (args.forcepng):
        fitsfiles.forcepng = args.forcepng
    count = fitsfiles.findNewFits(fitsfiles.fitspath, fitsdb)

    print("Successfully added {} images".format(count))


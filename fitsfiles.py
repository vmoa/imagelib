#
# fitsfile.py -- file manipulation routines
#

import argparse
import json
import os
import re
import sys

import fitsdb

# thuban:imagelib dlk$ find fits -name '*\.fits'
# fits/Eagle/SkyX/Images/ 2023-05-20/NGC 5457 2023-05-20 LUMEN 2x2 60.000secs 00005177.fits
# fits/Eagle/SkyX/Images/ 2023-05-20/NGC 5457 2023-05-20 LUMEN 2x2 90.000secs 00005171.fits


class FitsFiles:

    imagedb = list()
    name_ndx = dict()
    date_ndx = dict()

    fitspath = '/home/nas/Eagle/SkyX/Images'
    forcepng = False

    # Build this from file?
    ngc_catalog = {
        'NGC 1952': 'M1',
        'NGC 5457': 'M101',
    }

    def __init__(self):
        pass

    def fetchFits(self, path):
        '''Descend into `path` and build a database (dictionary for now) of all our FITS images.'''
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

        #print(image)
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
        cache_dir = '.'
        ts_file = cache_dir + '/.last_run'
        if (os.path.exists(ts_file)):
            newer_arg = '-newer ' + ts_file
        else:
            newer_arg = '';

        find_cmd = "find {} {} -name '*\.fits'".format(path, newer_arg)
        print("DEBUG: " + find_cmd)
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
                    print("\nPath: {}".format(fullpath))
                    (p,t) = self.fits2png(image)
                    image['preview'] = p
                    image['thumbnail'] = t
                    #dbstash(image)
                    fitsdb.insert(image)
                    print('  ', image)

    def dbstash(self, image):
        '''Stash `image` into imagedb and build appropriate indexes.'''
        imagedb.append(image)
        ndx = len(imagedb) - 1  # This is the primary key for indexes

        # Collect some shorthands to make indexing code more redable
        date = image['date']
        names = list()
        names.append(image['target'])
        if ('altname' in image):
            names.append(image['altname'])

        # Build date_ndx[date][name] = list of image ndx's
        if (date not in date_ndx):
            print("Initializing date_ndx[{}]".format(date))
            date_ndx[date] = dict()
        for name in names:
            if (name not in date_ndx[date]):
                print("Initializing date_ndx[{}][{}]".format(date,name))
                date_ndx[date][name] = list()
            date_ndx[date][name].append(ndx)

        # Build name_ndx[name][date] = list of image ndx's
        for name in names:
            if (name not in name_ndx):
                print("Initializing name_ndx[{}]".format(name))
                name_ndx[name] = dict()
            if (date not in name_ndx[name]):
                print("Initializing name_ndx[{}][{}]".format(name,date))
                name_ndx[name][date] = list()
            name_ndx[name][date].append(ndx)

    def loadOldDb():
        pass

    def saveNewDb():
        print(json.dumps(imagedb, indent=4))
        print(json.dumps(date_ndx, indent=4))
        print(json.dumps(name_ndx, indent=4))
        pass

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
    fitsfiles.findNewFits(fitsfiles.fitspath, fitsdb)


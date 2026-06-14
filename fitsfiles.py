#
# fitsfile.py -- file manipulation routines
#

import argparse
import datetime
import logging
import json
import os
import re
import sys
import subprocess   # Use subprocess for safer command execution

from astropy.io import fits

import catalog
import fitsdb

class FitsFiles:

    if (os.path.exists('/home/nas/Eagle')):
        fitspath = '/home/nas/Eagle'
    else:
        fitspath = 'Eagle'

    forcepng = False

    # Patterns of FITS filenames to search for (used to build `find` args dynamically)
    FILE_PATTERNS = ['*.fits', '*.fit', '*.fits.fz']

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
        logging.debug(">>> IMAGETYP: <{}>".format(headers['IMAGETYP'].lower()))
        if ('IMAGETYP' in headers and headers['IMAGETYP'].lower() in self.CFrames.keys()):
            record['target'] = "{} {}s".format(self.CFrames[headers['IMAGETYP'].lower()], int(headers['EXPTIME']))
            record['imagetype'] = 'cal'
        else:
            record['target'] = catalog.Catalog.cname(record['object'])
            record['imagetype'] = 'tgt'

        record['timestamp'] = headers['DATE-OBS']           # ISO 8601 (GMT) eg: 2023-05-20T05:41:18.042
        datestr = headers['DATE-OBS']
        # Split at the decimal, truncate fraction to 6 digits because NINA gives 7 digits
        if '.' in datestr:
            base, frac = datestr.split('.')
            frac = frac[:6] # truncate extra digits
            datestr = f"{base}.{frac}"
        record['date'] = datetime.datetime.fromisoformat(datestr).strftime('%Y-%m-%d')  # YYYY-MM-DD (GMT) convenient for sorting
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

        fits_path_abs = record['path']
        fits_dir = os.path.dirname(fits_path_abs)
        fits_filename = os.path.basename(fits_path_abs)

        if not os.path.exists(fits_path_abs) or not os.access(fits_path_abs, os.R_OK):
            logging.error(f"FATAL: FITS file not found or unreadable: {fits_path_abs}")
            return record

        # Define the intended final absolute paths
        preview_final_abs = fits_path_abs[:-5] + '.png'
        thumb_final_abs = fits_path_abs[:-5] + '-thumb.png'

        # --- WORKAROUND: Rename the file temporarily to a simple name ---
        # Create a safe, temporary filename within the same directory
        temp_safe_fits_path = os.path.join(fits_dir, "temp_safe_image.fits")

        try:
            # Rename the complex file path to the simple file path
            os.rename(fits_path_abs, temp_safe_fits_path)
            logging.info(f"Temporarily renamed file for fitspng compatibility.")

            # --- Now process using the simple name ---
            # The preview and thumb will also use simple names temporarily
            temp_safe_preview = os.path.join(fits_dir, "temp_safe_image.png")
            temp_safe_thumb = os.path.join(fits_dir, "temp_safe_image-thumb.png")

            # Preview Generation
            if (self.forcepng or not os.path.exists(preview_final_abs)):
                cmd = ['fitspng', '-o', temp_safe_preview, temp_safe_fits_path]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    # Move result to final name
                    os.rename(temp_safe_preview, preview_final_abs)
                    logging.info(f"Generated preview: {preview_final_abs}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"fitspng failed for preview (temp file used): {e.stderr}")
            record['preview'] = preview_final_abs

            # Thumbnail Generation
            scaling = int(record['x'] / 128) + 1
            if (self.forcepng or not os.path.exists(thumb_final_abs)):
                cmd = ['fitspng', '-s', str(scaling), '-o', temp_safe_thumb, temp_safe_fits_path]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    # Move result to final name
                    os.rename(temp_safe_thumb, thumb_final_abs)
                    logging.info(f"Generated thumbnail: {thumb_final_abs}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"fitspng failed for thumbnail (temp file used): {e.stderr}")
            record['thumbnail'] = thumb_final_abs

        finally:
            # --- CRITICAL: Always rename the original file back ---
            if os.path.exists(temp_safe_fits_path):
                os.rename(temp_safe_fits_path, fits_path_abs)
                logging.info(f"Restored original filename: {fits_path_abs}")

            # Clean up temp files if they somehow got left behind (optional but good practice)
            if os.path.exists(temp_safe_preview) : os.unlink(temp_safe_preview)
            if os.path.exists(temp_safe_thumb) : os.unlink(temp_safe_thumb)


        return record

    def addFitsFile(self, filename):
        filename = filename.rstrip()
        if (not os.path.exists(filename)):
            print("Skipping {}: File not found!".format(filename))
            return(0)

        logging.info("Importing {}".format(filename))
        headers = self.parseFitsHeader(filename)
        if (not headers):
            return(0)
        record = self.buildDatabaseRecord(filename, headers)
        logging.debug(">>> addFitsFile: imagetype: {}".format(record['imagetype']))
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

        # Build the find command
        start_time = datetime.datetime.now()  # On the off chance new files come in during find
        newer_arg = '';
        if (os.path.exists(fitsdb.tsfile)):
            newer_arg = '-newer ' + fitsdb.tsfile
        name_tests = ' -o '.join([f"-name '{p}'" for p in self.FILE_PATTERNS])
        find_cmd = f"find {path} {newer_arg} -type f -a \( {name_tests} \)"
        logging.debug(f">>> {find_cmd}")

        # Do the find comamand
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
    parser.add_argument('--debug', '-d', dest='debug', action='store_true', help='print diabolocal debugging dregs')
    parser.add_argument('--fitspath', '-f', dest='fitspath', action='store', help='path to fits files')
    parser.add_argument('--forcepng', '-p', dest='forcepng', action='store_true', help='force regeneration of PNG files even if they exist')
    parser.add_argument('file', nargs='*', help='full path to file to add (may be repeated)')
    args = parser.parse_args()

    if (args.debug):
        logging.basicConfig(level=logging.DEBUG)
        logging.debug("Dumping DEBUG drivel to your display")

    fitsdb = fitsdb.Fitsdb()

    fitsfiles = FitsFiles()
    if (args.fitspath):
        fitsfiles.fitspath = args.fitspath
    if (args.forcepng):
        fitsfiles.forcepng = args.forcepng
    count = fitsfiles.findNewFits(fitsfiles.fitspath, fitsdb, files=args.file)

    print("Successfully added {} images".format(count))


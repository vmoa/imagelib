import os
import re
import sys

# https://stackoverflow.com/questions/98135/how-do-i-use-django-templates-without-the-rest-of-django

from django.template import Template, Context
from django.template.loader import get_template
from django.conf import settings

settings.configure(TEMPLATES=[
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['.'], # if you want the templates from a file
        'APP_DIRS': False, # we have no apps
    },
])

import django
django.setup()

# Build static context dictionary; this should be done by walking directory tree
collections = {
    'title': 'RFO Image Library Thingy',
    'collections': [
        {
            'id': 'pic',
            'prefix': 'pic',
            'title': 'Random Pictures',
            'pics': [

                {
                    'id': 'pic001',
                    'title': 'M51',
                    'src': 'm51.jpg',
                },
                {
                    'id': 'pic002',
                    'title': 'M54',
                    'src': 'm54.jpg',
                },
                {
                    'id': 'pic003',
                    'title': 'M57',
                    'src': 'm57.jpg',
                },

                {
                    'id': 'pic004',
                    'title': 'M51',
                    'src': 'm51.jpg',
                },
                {
                    'id': 'pic005',
                    'title': 'M54',
                    'src': 'm54.jpg',
                },
                {
                    'id': 'pic006',
                    'title': 'M57',
                    'src': 'm57.jpg',
                },

                {
                    'id': 'pic007',
                    'title': 'M51',
                    'src': 'm51.jpg',
                },
                {
                    'id': 'pic008',
                    'title': 'M54',
                    'src': 'm54.jpg',
                },
                {
                    'id': 'pic009',
                    'title': 'M57',
                    'src': 'm57.jpg',
                },

                {
                    'id': 'pic010',
                    'title': 'M51',
                    'src': 'm51.jpg',
                },
                {
                    'id': 'pic011',
                    'title': 'M54',
                    'src': 'm54.jpg',
                },
                {
                    'id': 'pic012',
                    'title': 'M57',
                    'src': 'm57.jpg',
                },

            ],
        },
        {
            'id': 'pic2',
            'title': 'Not So Random Pictures',
            'pics': [
                {
                    'id': 'pic2007',
                    'title': 'M51',
                    'src': 'm51.jpg',
                },
                {
                    'id': 'pic2008',
                    'title': 'M54',
                    'src': 'm54.jpg',
                },
                {
                    'id': 'pic2009',
                    'title': 'M57',
                    'src': 'm57.jpg',
                },
            ],
        },
    ],
}

def fetchFits(path):
    '''Descend into `path` and build a database (dictionary for now) of all our FITS images.'''
    pass

ngc_catalog = {
    'NGC 1952': 'M1',
    'NGC 5457': 'M101',
}

class Image:
   def __init__(self):
        pass 

def parseFilename(filename):
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

        sequence_re = re.compile('^\d{8}$')
        if (sequence_re.fullmatch(thang)):
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
    if (target in ngc_catalog):
        image["target"] = ngc_catalog[target]
        image["altname"] = target
    else:
        image["target"] = target

    #print(image)
    return(image)

def findNewFits(path):
    '''Find new FITS files since last time we were run.  Runs the `find` system command on `path` to
       locate *.fits newer than `ts_file`.
       TBD: Stash the results in a list and build indexes into the list.```
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
                image = parseFilename(filename)
                image["date"] = m.group(0)
                image["path"] = fullpath

                print("\nPath: {}".format(fullpath))
                print('  ', image)

# thuban:imagelib dlk$ find fits -name '*\.fits'
# fits/Eagle/SkyX/Images/ 2023-05-20/NGC 5457 2023-05-20 LUMEN 2x2 60.000secs 00005177.fits
# fits/Eagle/SkyX/Images/ 2023-05-20/NGC 5457 2023-05-20 LUMEN 2x2 90.000secs 00005171.fits

findNewFits('fits')
sys.exit()

    

t = get_template('markup.django')
print(t.render(collections))


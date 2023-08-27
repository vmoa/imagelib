# RFO Image Library Code

Welcome to the RFO Image Library.  It renders png previews of FITs files captured at RFO and provides searching (soon) and downloading of the fits files.

* `fitsdb.py`: database management library and CLI.  Uses SQLite3.
* `fitsfiles.py`: filesystem management CLI.  It is run from cron and searches for new fits files to add to the database.
* `__init__.py`: Flask entrypoint for serving web pages.
* `imagelib.wsgi`: WSGI interface for `__init__.py`.  Used by the production Apache server.
* `markup.py`: library to build the Jinja dictionary for parsing `template/imagelib.html`.

Also:

* `templates/imagelib.html`: Jinja template used to render the web page.
* `static/imagelib.css`: CSS styles used by `templates/imagelib.html`.
* `static/imagelib.js`: Javascript code used to manipulate the web page.
* `static/*.png`: Various buttons used on the web page.

## Dependencies

* fitspng from https://integral.physics.muni.cz/fitspng/
  * Linux: `sudo apt-get install fitspng`
  * Mac: download and build source (requires `cfitsio` and `libpng`)

* Flask
  * Linux: `sudo apt-get install python3-flask`
  * Mac: `pip3 install flask`

* astroy (future)
  * Linux: `sudo apt-get install python3-astropy`
  * Mac: `pip3 install astropy`

* SQLite3 (which is conveniently built into most Python distributions)

* Awesomplete (by Lea Verou)

```
cd $src/static
git clone https://github.com/LeaVerou/awesomplete
```

## Reset database

```
rm fits.db fits.last_run
python3 fitsdb.py create
python3 fitsfiles.py
```

## Configure Apache WSGI

```
sudo apt-get install libapache2-mod-wsgi-py3
cp etc/100-imagelib.conf /etc/apache2/sites-available
sudo a2ensite 100-imagelib
```

* Install and configure virtual env 

```
virtualenv venv
. ./venv/bin/activate
pip install Flask
pip install django  (figure out how to use Flask instead)
ln -s ../../Eagle .
```

* Build database

```
mkdir /home/nas/data
python3 fitsdb.py create
python3 fitsfiles.py
```

* Test by hand

```
. ./venv/bin/activate
python3 ./__init__.py
```

* Reload apache

```
sudo apachectl reload
```

## Debugging

* Run by hand

```
flask --debug --app __init__.py run
```


## Thoughts

I expect we'll have two entrypoints, one to handle cron jobs and maintenance, the other to handle dynamic web requests.

If SQLite becomes too cumbersome, we can use the AWS MySQL instance, but that means all dev machines will need MySQL
as well, and that might be cumbersome.

## Images from Atik 16200

* 1x1 binning = 4498 x 3598
* 2x2 binning = 2249 x 1799
* 3x3 binning = 1499 x 1199 

## Markup structure

This is the dictionary passed to the template rendering engine.

```
    'title': 'RFO Image Library: ...',      # Page title
    'next': 'YYYY-MM-DD',                   # Date to start next page
    'collections': [                        # Array of date keyed collections
        {
            'id': 'rfo_YYYY-MM-DD',         # Unique identifier for this date
            'prefix': 'rfo_YYYY-MM-DD',     # Same as `id`, but used for selection
            'title': 'YYYY-MM-DD',          # Title of this collection
            'pics': [                       # Array of images (thumbnails) in this collection
                {
                    'id': 'rfo_YYYY-MM-DD_001',  # Unique identfier for this thumbnail
                    'recid': '123',         # The SQLite fits.db record `id` for this image
                    'title': 'M51',         # Title of the thumbnail
                    'src': 'm51.jpg',       # Source path for the thumbnail image
                },
                {
                    'id': 'rfo_YYYY-MM-DD_002',
                    'recid': '124',
                    'title': 'M54',
                    'src': 'm54.jpg',
                },
        },
        {
            'id': 'rfo_YYYY-MM-DD',
            'prefix': 'rfo_YYYY-MM-DD',
            'title': 'YYYY-MM-DD',
            ...
        },
        ...
    ]
```

## FITS header fields

These are (likely) all the header fields we have available.  We only save the ones we deem <i>important</i>
in the database.

```
$ fitsheader 'Dark 2x2 120.000secs 00006862.fits'
# HDU 0 in Dark 2x2 120.000secs 00006862.fits:
SIMPLE  =                    T / file does conform to FITS standard
BITPIX  =                   16 / number of bits per data pixel
NAXIS   =                    2 / number of data axes
NAXIS1  =                 2249 / length of data axis 1
NAXIS2  =                 1799 / length of data axis 2
EXTEND  =                    T / FITS dataset may contain extensions
COMMENT   FITS (Flexible Image Transport System) format is defined in 'Astronomy
COMMENT   and Astrophysics', volume 376, page 359; bibcode: 2001A&A...376..359H
BZERO   =                32768 / offset data range to that of unsigned short
BSCALE  =                    1 / default scaling factor
SBUUID  = '{504c0794-e3f8-41a2-9e7c-6820ea33c6cb}' / Photo UUID
EXPTIME =                 120. / SBIGFITSEXT Total exposure time in seconds
SWCREATE= 'TheSkyX Version 10.5.0 Build 12978' / SBIGFITSEXT Name & version of s
COLORCCD=                    0 / Non zero if image is from a Bayer color ccd
DISPINCR=                    1 / Non zero to automatically display the image in
PICTTYPE=                    3 / Image type as index 0= Unknown 1=Light, 2=Bias,
IMAGETYP= 'Dark Frame'         / SBIGFITSEXT Light, Dark, Bias or Flat
XORGSUBF=                    0 / SBIGFITSEXT Subframe x upper-left pixel in bin
YORGSUBF=                    0 / SBIGFITSEXT Subframe y upper-left pixel in bin
XBINNING=                    2 / SBIGFITSEXT Binning factor in width
YBINNING=                    2 / SBIGFITSEXT Binning factor in height
CCD-TEMP=               -20.02 / SBIGFITSEXT Temperature of the CCD
SET-TEMP=                 -20. / SBIGFITSEXT The cooler setpoint in degrees C
SITELAT = '+38 26 18.00'       / SBIGFITSEXT Latitude of the imaging location
SITELONG= '+122 30 31.00'      / SBIGFITSEXT Longitude of the imaging location
LST     = '+16 02 59.58'       / Local sidereal time
OBSGEO-B=        38.4383333333 / Latitude of the observation in degrees, North +
OBSGEO-L=      -122.5086111111 / Longitude of the observation in degrees, East +
OBSGEO-H=                 389. / Altitude of the observation in meters
OBJCTRA = '14 45 19.847'       / SBIGFITSEXT The right ascension of the center o
OBJCTDEC= '+38 15 59.60'       / SBIGFITSEXT The declination of the center of th
OBJECT  = 'A       '           / SBIGFITSEXT The name of the object imaged
INSTRUME= 'ASCOM Camera'       / SBIGFITSEXT The model camera used.
XPIXSZ  =                  12. / SBIGFITSEXT Pixel width in microns after binnin
YPIXSZ  =                  12. / SBIGFITSEXT Pixel height in microns after binni
DATE-OBS= '2023-08-15T02:40:00.466' / SBIGFITSEXT UTC of start exp. in ISO 8601
LOCALTIM= '8/14/2023 07:40:00.470 PM DST' / Local time at exposure start
```

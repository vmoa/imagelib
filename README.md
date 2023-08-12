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

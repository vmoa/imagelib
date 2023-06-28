


## Dependencies

* fitspng
  * cfitsio
  * libpng

Either
* pip3 install flask
* sudo apt-get install python3-flask

pip3 install astropy

pip3 install Django
https://stackoverflow.com/questions/98135/how-do-i-use-django-templates-without-the-rest-of-django
https://docs.djangoproject.com/en/dev/ref/templates/api/#configuring-the-template-system-in-standalone-mode

Uses SQLite3 which is conveniently built into Python

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



## Thoughts

I expect we'll have two entrypoints, one to handle cron jobs and maintenance, the other to handle dynamic web requests.

If SQLite becomes too cumbersome, we can use the AWS MySQL instance, but that means all dev machines will need MySQL
as well, and that might be cumbersome.

## Images

1x1 binning = 4498 x 3598
2x2 binning = 2249 x 1799
3x3 binning = 1499 x 1199 

### Markup structure

This is the dictionary passed to the template rendering engine.

'''
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
                    'title': 'M51',         # Title of the thumbnail
                    'src': 'm51.jpg',       # Source path for the thumbnail image
                },
                {
                    'id': 'rfo_YYYY-MM-DD_002',
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
'''




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

## Thoughts

I expect we'll have two entrypoints, one to handle cron jobs and maintenance, the other to handle dynamic web requests.

If SQLite becomes too cumbersome, we can use the AWS MySQL instance, but that means all dev machines will need MySQL
as well, and that might be cumbersome.

## Images

1x1 binning = 4498 x 3598
2x2 binning = 2249 x 1799
3x3 binning = 1499 x 1199 

### Markup structure

'''
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
'''

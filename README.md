


## Dependencies

* fitspng
  * cfitsio
  * libpng

pip3 install Django
https://stackoverflow.com/questions/98135/how-do-i-use-django-templates-without-the-rest-of-django
https://docs.djangoproject.com/en/dev/ref/templates/api/#configuring-the-template-system-in-standalone-mode

Uses SQLite3 which is conveniently built into Python

## Thoughts

I expect we'll have two entrypoints, one to handle cron jobs and maintenance, the other to handle dynamic web requests.

If SQLite becomes too cumbersome, we can use the AWS MySQL instance, but that means all dev machines will need MySQL
as well, and that might be cumbersome.

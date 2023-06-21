#
# markup.py -- django markup routines
#

import json
import os
import re
import sys

# https://stackoverflow.com/questions/98135/how-do-i-use-django-templates-without-the-rest-of-django
from django.template import Template, Context
from django.template.loader import get_template
from django.conf import settings
import django

import fitsdb


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


class Markup:

    def __init__(self):

        django.conf.settings.configure(TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': ['.'], # if you want the templates from a file
                'APP_DIRS': False, # we have no apps
            },
        ])

        django.setup()



if (__name__ == "__main__"):

    markup = Markup()

    db = fitsdb.Fitsdb()

    dates = list()
    rows = db.cur.execute("select distinct(date) from fits order by date desc").fetchall()
    for row in rows:
        dates.append(row[0])

    images = dict()
    images["title"] = "RFO Image Library: All"
    images["collections"] = list()

    for date in dates:

        collection = dict()
        prefix = "rfo_{}".format(date)
        collection["id"] = prefix
        collection["prefix"] = prefix
        collection["title"] = date
        collection["pics"] = list()

        sequence = 0
        rows = db.cur.execute("select target, altname, thumbnail, preview from fits where date = '{}' order by id".format(date)).fetchall()
        for row in rows:
            target, altname, thumbnail, preview = row
            if (thumbnail[0:15] == '/home/nas/Eagle'):
                thumbnail = thumbnail[10:]
            sequence += 1
            pic = dict()
            pic["id"] = "{}_{:03d}".format(prefix, sequence)
            pic["title"] = target
            if (altname):
                pic["title"] += " ({})".format(altname)
            pic["src"] = thumbnail
            pic["preview"] = preview  # Not used cuz I couln't figure out how to sneak it in
            collection["pics"].append(pic)

        images["collections"].append(collection)

    # print(json.dumps(images, indent=4))

    t = django.template.loader.get_template('markup.django')
    print(t.render(images))

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


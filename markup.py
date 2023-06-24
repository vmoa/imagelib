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

class Markup:

    db = fitsdb.Fitsdb()

    def __init__(self):
        django.conf.settings.configure(TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': ['.'], # if you want the templates from a file
                'APP_DIRS': False, # we have no apps
            },
        ])
        django.setup()

    def markup(self):

        dates = list()
        rows = self.db.cur.execute("select distinct(date) from fits order by date desc").fetchall()
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
            rows = self.db.cur.execute("select target, altname, thumbnail, preview from fits where date = '{}' order by id".format(date)).fetchall()
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
        return(t.render(images))



if (__name__ == "__main__"):

    markup = Markup()
    page = markup.markup()
    print(page)

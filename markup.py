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
    thumb_max = 64    # Number of thumbnails to display (rounded up to fill the grouping)

    def __init__(self):
        django.conf.settings.configure(TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': ['.'], # if you want the templates from a file
                'APP_DIRS': False, # we have no apps
            },
        ])
        django.setup()

    def build_images(self, start=None):
        '''Build a template (dictionary) of which images to display.'''
        dates = list()
        cur = self.db.con.cursor()
        if (start):
            rows = cur.execute("select distinct(date) from fits where date <= ? order by date desc", (start,)).fetchall()
        else:
            rows = cur.execute("select distinct(date) from fits order by date desc").fetchall()
        for row in rows:
            dates.append(row[0])

        images = dict()
        images["title"] = "RFO Image Library: All"
        images["collections"] = list()

        thumb_count = 0
        for date in dates:

            if (thumb_count >= self.thumb_max):
                images["next"] = date
                break

            collection = dict()
            prefix = "rfo_{}".format(date)
            collection["id"] = prefix
            collection["prefix"] = prefix
            collection["title"] = date
            collection["pics"] = list()

            sequence = 0
            rows = cur.execute("select target, altname, thumbnail, preview from fits where date = '{}' order by id".format(date)).fetchall()
            for row in rows:
                thumb_count += 1
                sequence += 1
                target, altname, thumbnail, preview = row
                if (thumbnail[0:15] == '/home/nas/Eagle'):
                    thumbnail = thumbnail[10:]
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
        return(images)

    def markup(self):
        images = self.build_images()
        t = django.template.loader.get_template('templates/imagelib.html')
        return(t.render(images))



if (__name__ == "__main__"):

    markup = Markup()
    page = markup.markup()
    print(page)

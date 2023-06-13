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

t = get_template('markup.django')
print(t.render(collections))


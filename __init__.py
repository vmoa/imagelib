#
# imagelib main web interface
#

prodhome = "/home/nas/flask/imagelib"
import os
import sys
if (os.path.exists(prodhome)):
    sys.path.insert(0, prodhome)
else:
    sys.path.insert(0, ".")

from logging.config import dictConfig
dictConfig({
    'version': 1,
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

import flask
app = flask.Flask(__name__)
app.secret_key = 'allyourbasearebelongtous'

import markup
markup = markup.Markup()


#
# Register URL callbacks
#

@app.route('/', methods=['GET','POST'])
def top():
    print("Args: ", flask.request.args.to_dict(), " Form: ", flask.request.form.to_dict())
    t = markup.build_images(start = flask.request.form.get('start'),
                            target = flask.request.form.get('target'),
                            imgfilter = flask.request.form.get('imgfilter'),
                            lastTarget = flask.request.form.get('last_target'))
    return flask.render_template('imagelib.html', **t)

@app.route('/search', methods=['GET','POST'])
def search():
    print("Args: ", flask.request.args.to_dict(), " Form: ", flask.request.form.to_dict())
    target = flask.request.args.get('target')
    app.logger.info("DEBUG: search target={}".format(target))
    t = markup.build_images(target = target)
    return flask.render_template('imagelib.html', **t)

@app.route('/download', methods=['GET','POST'])
def download():
    app.logger.info("DEBUG: download({})".format(flask.request.form.get('recids')))
    tempfn = markup.zipit(flask.request.form.get('recids'))
    app.logger.info("DEBUG: sending {}".format(tempfn))
    response = flask.send_file(tempfn, as_attachment=True)
    return response
    # unlink(tempfn)

@app.route('/deets', methods=['GET'])
def deets():
    recid = flask.request.args.get('recid')
    app.logger.info("DEBUG: deets({})".format(recid))
    return flask.render_template_string(markup.fetchDeets(recid))

@app.route('/favicon.ico')
def favicon():
    return flask.send_file('static/dob16.png')

# DEBUG HACK; should make it so Apache deals with this
@app.route('/fits/<path:path>')
def fits(path):
    return flask.send_file('fits/' + path)

# FLASK HACK; should make it so Apache deals with this
@app.route('/Eagle/<path:path>')
def eagle(path):
    return flask.send_file('Eagle/' + path)


# For testing by hand
if __name__ == '__main__':
    app.run('0.0.0.0', 5000)


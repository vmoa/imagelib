#
# imagelib.py -- main web interface
#

import flask
app = flask.Flask(__name__)

import markup
markup = markup.Markup()


#
# Register URL callbacks
#

@app.route('/', methods=['GET','POST'])
def top():
    print("Args: ", flask.request.args.to_dict(), " Form: ", flask.request.form.to_dict())
    t = markup.build_images(flask.request.form.get('start'))
    return flask.render_template('imagelib.html', **t)

# DEBUG HACK; should make it so Apache deals with this
@app.route('/fits/<path:path>')
def fits(path):
    return flask.send_file('fits/' + path)


if __name__ == '__main__':
    app.run('0.0.0.0', 5000)





import flask
app = flask.Flask(__name__)

import markup
markup = markup.Markup()


#
# Register URL callbacks
#

@app.route('/')
def top():
    t = markup.build_images()
    return flask.render_template('imagelib.html', **t)

# DEBUG HACK; should make it so Apache deals with this
@app.route('/fits/<path:path>')
def fits(path):
    app.logger.info(path)
    return flask.send_file('fits/' + path)



@app.route('/startstop', methods=['GET'])
def startStop():
    """User pressed the Start/Stop button"""
    return browser.browser.startStop(app)

@app.route('/connect', methods=['GET'])
def connect():
    """Browser connected to T-Rax; dispatch welcome message and connect brower to SSE stream"""
    logging.info("Browser connected from {}".format(flask.request.remote_addr))
    threading.Timer(0.5, browser.browser.initialConnect).start()  # Dispatch our welcome connect function
    return flask.Response(sse.sse.stream(), mimetype='text/event-stream')



if __name__ == '__main__':
    #initialize()
    app.run('0.0.0.0', 5000)


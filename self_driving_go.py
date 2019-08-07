# Dexter Industries GoPiGo3 Remote Camera robot
# With this project you can control your Raspberry Pi Robot, the GoPiGo3, with a phone, tablet, or browser.
# Remotely view your robot as first person in your browser.
#
# You MUST run this with python3
# To Run:  python3 flask_server.py

import signal
import sys
import logging
import datetime
import numpy as np
import os
import shutil
from time import sleep
import tensorflow as tf
from keras.models import load_model
import base64
from io import BytesIO
from PIL import Image
import cv2

global graph, model
graph = tf.get_default_graph()

# check if it's ran with Python3
assert sys.version_info[0:1] == (3,)

# imports needed for web server
from flask import Flask, jsonify, render_template, request, Response, send_from_directory, url_for
from werkzeug.serving import make_server
from gopigo3 import FirmwareVersionError
from easygopigo3 import EasyGoPiGo3

# imports needed for stream server
import io
import picamera
import socketserver
from threading import Condition, Thread, Event
from http import server

logging.basicConfig(level = logging.DEBUG)

# for triggering the shutdown procedure when a signal is detected
keyboard_trigger = Event()
def signal_handler(signal, frame):
    logging.info('Signal detected. Stopping threads.')
    keyboard_trigger.set()

speed_limit = 10
def img_preprocess(img):
    try:
        img = img[100:300,:,:] # ignore upper 100 pixels
        img = cv2.cvtColor(img, cv2.COLOR_RGB2YUV)
        img = cv2.GaussianBlur(img,  (3, 3), 0)
        img = cv2.resize(img, (200, 66))
        img = img/255
    except Exception as e:
        logging.warning('Image processing is not going well. ', e)

    return img

#######################
### Web Server Stuff ##
#######################

# Directory Path can change depending on where you install this file.  Non-standard installations
# may require you to change this directory.
directory_path = '/home/pi/Dexter/GoPiGo3/Projects/RemoteCameraRobot/static'
training_path = '/home/pi/test/training'
data_file = training_path + '/' + 'training_data.csv'

MAX_FORCE = 5.0
MIN_SPEED = 100
MAX_SPEED = 300
try:
    gopigo3_robot = EasyGoPiGo3()
except IOError:
    logging.critical('GoPiGo3 is not detected.')
    sys.exit(1)
except FirmwareVersionError:
    logging.critical('GoPiGo3 firmware needs to be updated')
    sys.exit(2)
except Exception:
    logging.critical("Unexpected error when initializing GoPiGo3 object")
    sys.exit(3)

HOST = "0.0.0.0"
WEB_PORT = 5000
app = Flask(__name__, static_url_path='')

state = 'stop'
angle_degrees = 0
angle_dir = ''
force = 0

class WebServerThread(Thread):
    '''
    Class to make the launch of the flask server non-blocking.
    Also adds shutdown functionality to it.
    '''
    def __init__(self, app, host, port):
        Thread.__init__(self)
        self.srv = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        logging.info('Starting Flask server')
        self.srv.serve_forever()

    def shutdown(self):
        logging.info('Stopping Flask server')
        self.srv.shutdown()

@app.route("/robot", methods = ["POST"])
def get_commands():
    global state
    args = request.args
    state = args['state']

    resp = Response()
    resp.mimetype = "application/json"
    resp.status = "OK"
    resp.status_code = 200

    return resp

def robot_commands(angle_degrees):
    angle_dir = 'self'
    force = 1.5 # //float(args['force'])
    #
    determined_speed = MIN_SPEED + force * (MAX_SPEED - MIN_SPEED) / MAX_FORCE
    if determined_speed > MAX_SPEED:
        determined_speed = MAX_SPEED

    if state == 'move':
        gopigo3_robot.open_eyes()
        # for moving backward
        if angle_degrees >= 260 and angle_degrees <= 280:
            gopigo3_robot.set_speed(determined_speed)
            gopigo3_robot.backward()

        # for moving to the left or forward
        if angle_degrees == 90 :
            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_RIGHT, determined_speed)
            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_LEFT, determined_speed)

        if angle_degrees > 90 and angle_degrees < 260:
            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_RIGHT, determined_speed)

            left_motor_percentage = abs((angle_degrees - 170) / 90)
            sign = -1 if angle_degrees >= 180 else 1

            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_LEFT, determined_speed * left_motor_percentage * sign)

        # for moving to the right (or forward)- upper half
        if angle_degrees < 90 and angle_degrees >= 0:
            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_LEFT, determined_speed)

            right_motor_percentage = angle_degrees / 90
            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_RIGHT, determined_speed * right_motor_percentage)
        # for moving to the right (or forward)- bottom half
        if angle_degrees <= 360 and angle_degrees > 280:
            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_LEFT, determined_speed)

            right_motor_percentage = (angle_degrees - 280) / 80 - 1
            gopigo3_robot.set_motor_dps(gopigo3_robot.MOTOR_RIGHT, determined_speed * right_motor_percentage)

    elif state == 'stop':
        gopigo3_robot.close_eyes()
        gopigo3_robot.stop()
    else:
        app.logging.warning('unknown state sent')

    resp = Response()
    resp.mimetype = "application/json"
    resp.status = "OK"
    resp.status_code = 200

    return resp

@app.route("/")
def index():
    return page("index.html")

@app.route("/<string:page_name>")
def page(page_name):
    return render_template("{}".format(page_name))

@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory(directory_path, path)

#############################
### Video Streaming Stuff ###
#############################

class StreamingOutput(object):
    '''
    Class to which the video output is written to.
    The buffer of this class is then read by StreamingHandler continuously.
    '''
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

class StreamingHandler(server.BaseHTTPRequestHandler):
    '''
    Implementing GET request for the video stream.
    '''
    def do_GET(self):
        if self.path == '/stream.mjpg':
            f = open(data_file, 'ab+')
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
                    # for self-driving
                    try:
                        image = Image.open(io.BytesIO(frame))
                        image = np.asarray(image)
                        image = img_preprocess(image)
                        image = np.array([image])
                        with graph.as_default():
                            angle_degrees = float(model.predict(image))
                        throttle = 1.5
                        print('{} {}'.format(angle_degrees, throttle))
                        robot_commands(angle_degrees)
                    except Exception as e:
                        logging.warning('Image is not ready. ', e)
                    # for training
                    # filename = 'center_' + datetime.datetime.now().strftime('%y_%m_%d_%H_%M_%S_%f') + '.jpg'
                    # outfilename = training_path + '/' + filename
                    # with open(outfilename, 'wb+') as outfile:
                    #     outfile.write(frame)
                    #
                    # determined_speed = MIN_SPEED + force * (MAX_SPEED - MIN_SPEED) / MAX_FORCE
                    # if determined_speed > MAX_SPEED:
                    #     determined_speed = MAX_SPEED
                    # data = np.array([filename, filename, filename, angle_degrees, force, angle_dir, determined_speed])
                    # # print(data)
                    # np.savetxt(f, np.column_stack(data), delimiter=',', fmt='%s')# , header='center, left, right, steering, throttle, reverse, speed')

            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
                f.close()
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def cleanup():
    gopigo3_robot.stop()

    if os.path.exists(training_path):
        shutil.rmtree(training_path)

    if os.path.exists(data_file):
        os.remove(data_file)

    if not os.path.exists(training_path):
        os.makedirs(training_path)

#############################
### Aggregating all calls ###
#############################

if __name__ == "__main__":
    #
    cleanup()
    # loading model
    model = load_model('model.h5')
    # registering both types of signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # firing up the video camera (pi camera)
    camera = picamera.PiCamera(resolution='320x240', framerate=10)
    output = StreamingOutput()
    camera.start_recording(output, format='mjpeg')
    logging.info("Started recording with picamera")
    STREAM_PORT = 5001
    stream = StreamingServer((HOST, STREAM_PORT), StreamingHandler)

    # starting the video streaming server
    streamserver = Thread(target = stream.serve_forever)
    streamserver.start()
    logging.info("Started stream server for picamera")

    # starting the web server
    webserver = WebServerThread(app, HOST, WEB_PORT)
    webserver.start()
    logging.info("Started Flask web server")

    # and run it indefinitely
    while not keyboard_trigger.is_set():
        sleep(0.5)

    # until some keyboard event is detected
    logging.info("Keyboard event detected")

    # trigger shutdown procedure
    webserver.shutdown()
    camera.stop_recording()
    stream.shutdown()

    # and finalize shutting them down
    webserver.join()
    streamserver.join()
    logging.info("Stopped all threads")

    sys.exit(0)

from configparser import ConfigParser

from flask import Flask
import raven

config = ConfigParser()
try:
	config.read('rubberband.conf')
except Exception as e:
	print("Something is wrong with your rubberband.conf file")
	print(e)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql+psycopg2://{}:{}@localhost/rubberband".format(
	config['postgres']['user'], config['postgres']['password'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.debug = config['rubberband']['debug']
app.secret_key = config['flask']['secret_key']

import rubberband.main

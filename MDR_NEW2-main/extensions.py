from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

mongo = PyMongo()
bcrypt = Bcrypt()
login_manager = LoginManager()

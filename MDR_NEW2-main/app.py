"""
MDR Disease Risk Prediction & Contact Tracing System
=====================================================
Main Flask Application Entry Point
"""

import os
import logging
from flask import Flask
from config import Config
from extensions import mongo, bcrypt, login_manager

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Init extensions
    mongo.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/app.log"),
            logging.StreamHandler()
        ]
    )

    # Register blueprints
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.doctor import doctor_bp
    from routes.user import user_bp
    from routes.api import api_bp
    from routes.uploads import uploads_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(doctor_bp, url_prefix="/doctor")
    app.register_blueprint(user_bp, url_prefix="/user")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(uploads_bp)

    # Create upload dirs
    os.makedirs(app.config["UPLOAD_FOLDER_PATIENTS"], exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER_FRAMES"], exist_ok=True)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)

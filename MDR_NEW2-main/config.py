"""
Configuration settings for MDR Application
"""

import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "mdr-super-secret-key-change-in-production-2024")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/mdr_disease_db")

    # Upload settings
    UPLOAD_FOLDER_PATIENTS = os.path.join(os.path.dirname(__file__), "uploads", "patients")
    UPLOAD_FOLDER_FRAMES   = os.path.join(os.path.dirname(__file__), "uploads", "frames")
    MAX_CONTENT_LENGTH     = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS     = {"png", "jpg", "jpeg", "gif", "bmp"}

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY    = True
    SESSION_COOKIE_SAMESITE    = "Lax"

    # Model directory
    MODEL_DIR = os.path.join(os.path.dirname(__file__), "model", "mdr_prediction_package", "mdr_model")

    # Face recognition
    FACE_RECOGNITION_TOLERANCE = 0.5
    FACE_RECOGNITION_MODEL     = "hog"   # 'hog' (CPU) or 'cnn' (GPU)

    # Contact tracing
    CONTACT_DISTANCE_THRESHOLD = 300      # pixels
    CONTACT_DURATION_THRESHOLD = 3        # seconds for a contact to count
    HIGH_RISK_EXPOSURE_SCORE   = 53       # score threshold for HIGH alert

    # PDF
    REPORTS_FOLDER = os.path.join(os.path.dirname(__file__), "uploads", "reports")

    # Email Settings (Gmail SMTP)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "your-email@gmail.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "your-gmail-app-password")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", MAIL_USERNAME)


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

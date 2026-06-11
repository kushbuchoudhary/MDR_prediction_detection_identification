"""
serve_uploads.py  — Registered as a blueprint to serve uploaded patient photos
from outside the static/ folder securely.
"""

import os
from flask import Blueprint, send_from_directory, abort, current_app
from flask_login import login_required

uploads_bp = Blueprint("uploads", __name__)


@uploads_bp.route("/uploads/patients/<filename>")
@login_required
def serve_patient_photo(filename):
    folder = current_app.config["UPLOAD_FOLDER_PATIENTS"]
    path   = os.path.join(folder, filename)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(folder, filename)


@uploads_bp.route("/uploads/frames/<filename>")
@login_required
def serve_frame(filename):
    folder = current_app.config["UPLOAD_FOLDER_FRAMES"]
    path   = os.path.join(folder, filename)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(folder, filename)

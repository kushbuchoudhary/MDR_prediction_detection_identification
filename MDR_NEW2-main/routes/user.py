"""
User Routes — Read-only view of own records
"""

import logging
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import mongo

user_bp = Blueprint("user", __name__)
logger  = logging.getLogger(__name__)


def user_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("user", "admin", "doctor"):
            flash("Login required.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@user_bp.route("/dashboard")
@login_required
@user_required
def dashboard():
    # Users see their own patient record (matched by username/email)
    patient = mongo.db.patients.find_one(
        {"$or": [{"assigned_user": current_user.username},
                 {"patient_email": current_user.email}]}
    )

    recent_alerts = list(mongo.db.alerts.find(
        {"patient_id": patient["patient_id"], "status": "active"} if patient else {"_id": None}
    ).sort("created_at", -1).limit(5))

    return render_template(
        "user/dashboard.html",
        patient=patient,
        recent_alerts=recent_alerts
    )


@user_bp.route("/my-records")
@login_required
@user_required
def my_records():
    patient = mongo.db.patients.find_one(
        {"$or": [{"assigned_user": current_user.username},
                 {"patient_email": current_user.email}]}
    )

    prediction = None
    contacts   = []
    reports    = []
    if patient:
        prediction = mongo.db.predictions.find_one(
            {"patient_id": patient["patient_id"]},
            sort=[("created_at", -1)]
        )
        contacts = list(mongo.db.contacts.find(
            {"$or": [{"person1_id": patient["patient_id"]},
                     {"person2_id": patient["patient_id"]}]}
        ).sort("start_time", -1).limit(10))
        reports = list(mongo.db.reports.find(
            {"patient_id": patient["patient_id"]}
        ).sort("created_at", -1))

    return render_template(
        "user/my_records.html",
        patient=patient, prediction=prediction,
        contacts=contacts, reports=reports
    )


@user_bp.route("/alerts")
@login_required
@user_required
def alerts():
    patient = mongo.db.patients.find_one(
        {"$or": [{"assigned_user": current_user.username},
                 {"patient_email": current_user.email}]}
    )

    alerts_list = []
    if patient:
        alerts_list = list(mongo.db.alerts.find(
            {"patient_id": patient["patient_id"], "status": "active"}
        ).sort("created_at", -1))

    return render_template("user/alerts.html", alerts=alerts_list, patient=patient)

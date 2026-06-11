"""
Admin Routes — Full system access
"""

import os
import logging
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, current_app, jsonify, send_file)
from flask_login import login_required, current_user
from functools import wraps
from extensions import mongo, bcrypt
from bson import ObjectId
from bson.json_util import dumps
import json

admin_bp = Blueprint("admin", __name__)
logger   = logging.getLogger(__name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    total_patients    = mongo.db.patients.count_documents({})
    mdr_positive      = mongo.db.patients.count_documents({"mdr_status": 1})
    high_risk         = mongo.db.predictions.count_documents({"risk_classification": "High"})
    active_contacts   = mongo.db.contacts.count_documents({"status": "active"})
    total_users       = mongo.db.users.count_documents({})
    total_doctors     = mongo.db.users.count_documents({"role": "doctor"})

    recent_alerts     = list(mongo.db.alerts.find({"status": "active"}).sort("created_at", -1).limit(10))
    recent_patients   = list(mongo.db.patients.find().sort("registration_date", -1).limit(8))

    # Chart data
    risk_dist = {
        "Low":    mongo.db.predictions.count_documents({"risk_classification": "Low"}),
        "Medium": mongo.db.predictions.count_documents({"risk_classification": "Medium"}),
        "High":   mongo.db.predictions.count_documents({"risk_classification": "High"}),
    }

    return render_template(
        "admin/dashboard.html",
        total_patients=total_patients, mdr_positive=mdr_positive,
        high_risk=high_risk, active_contacts=active_contacts,
        total_users=total_users, total_doctors=total_doctors,
        recent_alerts=recent_alerts, recent_patients=recent_patients,
        risk_dist=json.dumps(risk_dist)
    )


@admin_bp.route("/patients")
@login_required
@admin_required
def patients():
    patients_list = list(mongo.db.patients.find().sort("registration_date", -1))
    return render_template("admin/patients.html", patients=patients_list)


@admin_bp.route("/patients/<patient_id>")
@login_required
@admin_required
def patient_detail(patient_id):
    patient = mongo.db.patients.find_one({"patient_id": patient_id})
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for("admin.patients"))
    prediction = mongo.db.predictions.find_one({"patient_id": patient_id},
                                                sort=[("created_at", -1)])
    contacts   = list(mongo.db.contacts.find(
        {"$or": [{"person1_id": patient_id}, {"person2_id": patient_id}]}
    ).sort("start_time", -1).limit(20))
    return render_template("admin/patient_detail.html",
                           patient=patient, prediction=prediction, contacts=contacts)


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    users_list = list(mongo.db.users.find().sort("created_at", -1))
    return render_template("admin/users.html", users=users_list)


@admin_bp.route("/users/toggle/<user_id>", methods=["POST"])
@login_required
@admin_required
def toggle_user(user_id):
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if user:
        new_status = not user.get("is_active", True)
        mongo.db.users.update_one({"_id": ObjectId(user_id)},
                                   {"$set": {"is_active": new_status}})
        flash(f"User {'activated' if new_status else 'deactivated'}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/alerts")
@login_required
@admin_required
def alerts():
    alerts_list = list(mongo.db.alerts.find().sort("created_at", -1).limit(100))
    return render_template("admin/alerts.html", alerts=alerts_list)


@admin_bp.route("/alerts/dismiss/<alert_id>", methods=["POST"])
@login_required
@admin_required
def dismiss_alert(alert_id):
    mongo.db.alerts.update_one({"_id": ObjectId(alert_id)},
                                {"$set": {"status": "dismissed", "dismissed_by": current_user.username}})
    return jsonify({"success": True})


@admin_bp.route("/contacts")
@login_required
@admin_required
def contacts():
    contacts_list = list(mongo.db.contacts.find().sort("start_time", -1).limit(200))
    return render_template("admin/contacts.html", contacts=contacts_list)


@admin_bp.route("/reports")
@login_required
@admin_required
def reports():
    reports_list = list(mongo.db.reports.find().sort("created_at", -1))
    return render_template("admin/reports.html", reports=reports_list)


@admin_bp.route("/reports/download/<report_id>")
@login_required
@admin_required
def download_report(report_id):
    report = mongo.db.reports.find_one({"report_id": report_id})
    if not report:
        flash("Report not found.", "danger")
        return redirect(url_for("admin.reports"))
    filepath = report.get("filepath", "")
    if not os.path.exists(filepath):
        flash("Report file not found on disk.", "danger")
        return redirect(url_for("admin.reports"))
    return send_file(filepath, as_attachment=True, download_name=report.get("filename"))


@admin_bp.route("/monitoring")
@login_required
@admin_required
def monitoring():
    recent_alerts = list(mongo.db.alerts.find().sort("created_at", -1).limit(10))
    return render_template("admin/monitoring.html", recent_alerts=recent_alerts)


@admin_bp.route("/api/stats")
@login_required
@admin_required
def api_stats():
    """Real-time stats endpoint polled by dashboard."""
    return jsonify({
        "total_patients": mongo.db.patients.count_documents({}),
        "mdr_positive":   mongo.db.patients.count_documents({"mdr_status": 1}),
        "high_risk":      mongo.db.predictions.count_documents({"risk_classification": "High"}),
        "active_contacts":mongo.db.contacts.count_documents({"status": "active"}),
        "critical_alerts":mongo.db.alerts.count_documents({"alert_level": "CRITICAL", "status": "active"}),
    })

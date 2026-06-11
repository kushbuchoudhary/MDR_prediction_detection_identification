"""
REST API Routes — used by frontend JS for real-time updates
"""

import logging
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import mongo
from datetime import datetime

api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)


@api_bp.route("/dashboard-stats")
@login_required
def dashboard_stats():
    base = {}
    if current_user.role == "admin":
        base = {
            "total_patients":  mongo.db.patients.count_documents({}),
            "mdr_positive":    mongo.db.patients.count_documents({"mdr_status": 1}),
            "high_risk":       mongo.db.predictions.count_documents({"risk_classification": "High"}),
            "active_contacts": mongo.db.contacts.count_documents({"status": "active"}),
            "critical_alerts": mongo.db.alerts.count_documents({"alert_level": "CRITICAL", "status": "active"}),
            "total_users":     mongo.db.users.count_documents({}),
        }
    elif current_user.role == "doctor":
        base = {
            "total_patients":  mongo.db.patients.count_documents({}),
            "mdr_positive":    mongo.db.patients.count_documents({"mdr_status": 1}),
            "high_risk":       mongo.db.predictions.count_documents({"risk_classification": "High"}),
            "critical_alerts": mongo.db.alerts.count_documents({"alert_level": "CRITICAL", "status": "active"}),
        }
    return jsonify(base)


@api_bp.route("/recent-alerts")
@login_required
def recent_alerts():
    query = {"status": "active"}
    alerts = list(mongo.db.alerts.find(query, {"_id": 0}).sort("created_at", -1).limit(10))
    for a in alerts:
        if isinstance(a.get("created_at"), datetime):
            a["created_at"] = a["created_at"].strftime("%Y-%m-%d %H:%M")
    return jsonify({"alerts": alerts})


@api_bp.route("/patients-list")
@login_required
def patients_list():
    query = {}
    patients = list(mongo.db.patients.find(query, {
        "_id": 0, "patient_id": 1, "name": 1, "mdr_status": 1,
        "ward_type": 1, "registration_date": 1
    }).sort("registration_date", -1).limit(50))
    for p in patients:
        if isinstance(p.get("registration_date"), datetime):
            p["registration_date"] = p["registration_date"].strftime("%Y-%m-%d")
    return jsonify({"patients": patients})


@api_bp.route("/risk-distribution")
@login_required
def risk_distribution():
    query = {}
    dist = {
        "Low":    mongo.db.predictions.count_documents({**query, "risk_classification": "Low"}),
        "Medium": mongo.db.predictions.count_documents({**query, "risk_classification": "Medium"}),
        "High":   mongo.db.predictions.count_documents({**query, "risk_classification": "High"}),
    }
    return jsonify(dist)


@api_bp.route("/send-custom-alert", methods=["POST"])
@login_required
def send_custom_alert():
    if current_user.role not in ("admin", "doctor"):
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    
    data = request.get_json() or {}
    alert_type = data.get("type", "exposure")
    patient_id = data.get("patient_id")
    
    if not patient_id:
        return jsonify({"success": False, "error": "Missing patient_id"}), 400
        
    try:
        from utils.email_utils import send_high_risk_registration_alert, send_contact_exposure_alert
        if alert_type == "patient":
            patient = mongo.db.patients.find_one({"patient_id": patient_id})
            if patient:
                send_high_risk_registration_alert(patient_id, patient.get("name", "Unknown"), "CRITICAL", 0.95, "Priority manual review alert.")
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "Patient not found"}), 404
        else:
            contact = mongo.db.contacts.find_one({
                "$or": [{"person1_id": patient_id}, {"person2_id": patient_id}]
            }, sort=[("start_time", -1)])
            
            if contact:
                send_contact_exposure_alert(
                    contact["person1_id"], contact["person1_name"],
                    contact["person2_id"], contact["person2_name"],
                    contact.get("duration", 0), contact.get("exposure_score", 0),
                    contact.get("exposure_risk", "High"), contact.get("avg_proximity", 0)
                )
                return jsonify({"success": True})
            else:
                return jsonify({"success": False, "error": "No recent contact found for this entity"}), 404
    except Exception as e:
        logger.error(f"Failed to send manual alert: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


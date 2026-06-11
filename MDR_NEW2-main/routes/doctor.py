"""
Doctor Routes — Patient management, predictions, webcam monitoring
"""

import os
import io
import json
import logging
import base64
from datetime import datetime
from functools import wraps

import cv2
import numpy as np
from flask import (Blueprint, render_template, redirect, url_for, request,
                   flash, current_app, jsonify, Response, send_file)
from flask_login import login_required, current_user

from extensions import mongo
from utils.face_utils import (generate_face_embedding, match_face,
                               detect_faces_in_frame, get_face_encodings_from_frame,
                               draw_recognition_box, frame_to_base64, save_detected_face)
from utils.contact_tracing import ContactTracker, calculate_exposure_score, compute_final_risk, generate_recommendations
from utils.pdf_utils import generate_patient_report

doctor_bp = Blueprint("doctor", __name__)
logger    = logging.getLogger(__name__)

# Global contact tracker instance (per-process; fine for single-worker dev)
_contact_tracker = ContactTracker()


def doctor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("admin", "doctor"):
            flash("Doctor access required.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ──────────────────────────────────────────────────────────────────

@doctor_bp.route("/dashboard")
@login_required
@doctor_required
def dashboard():
    my_patients    = list(mongo.db.patients.find({}).sort("registration_date", -1).limit(10))
    total_assigned = mongo.db.patients.count_documents({})
    mdr_count      = mongo.db.patients.count_documents({"mdr_status": 1})
    high_risk      = mongo.db.predictions.count_documents({"risk_classification": "High"})
    recent_alerts  = list(mongo.db.alerts.find({"status": "active"}).sort("created_at", -1).limit(5))

    risk_dist = {
        "Low":    mongo.db.predictions.count_documents({"risk_classification": "Low"}),
        "Medium": mongo.db.predictions.count_documents({"risk_classification": "Medium"}),
        "High":   mongo.db.predictions.count_documents({"risk_classification": "High"}),
    }

    return render_template(
        "doctor/dashboard.html",
        my_patients=my_patients, total_assigned=total_assigned,
        mdr_count=mdr_count, high_risk=high_risk,
        recent_alerts=recent_alerts,
        risk_dist=json.dumps(risk_dist)
    )


@doctor_bp.route("/alerts/dismiss/<alert_id>", methods=["POST"])
@login_required
@doctor_required
def dismiss_alert(alert_id):
    from bson import ObjectId
    mongo.db.alerts.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"status": "dismissed", "dismissed_by": current_user.username}}
    )
    return jsonify({"success": True})



# ── Patient Registration ───────────────────────────────────────────────────────

@doctor_bp.route("/register-patient", methods=["GET", "POST"])
@login_required
@doctor_required
def register_patient():
    doctors = list(mongo.db.users.find({"role": "doctor"}))
    patient_users = list(mongo.db.users.find({"role": "user"}))

    if request.method == "POST":
        from model.mdr_predictor import MDRPredictor
        allowed_ext = current_app.config["ALLOWED_EXTENSIONS"]
        upload_dir  = current_app.config["UPLOAD_FOLDER_PATIENTS"]

        patient_id  = request.form.get("patient_id", "").strip().upper()
        name        = request.form.get("name", "").strip()

        if not patient_id or not name:
            flash("Patient ID and Name are required.", "danger")
            return render_template("doctor/register_patient.html", doctors=doctors, patient_users=patient_users)

        if mongo.db.patients.find_one({"patient_id": patient_id}):
            flash(f"Patient ID {patient_id} already exists.", "danger")
            return render_template("doctor/register_patient.html", doctors=doctors, patient_users=patient_users)

        # Get assigned info from form
        assigned_doctor = request.form.get("assigned_doctor") or current_user.username
        assigned_user = request.form.get("assigned_user") or None
        patient_email = None
        if assigned_user:
            user_doc = mongo.db.users.find_one({"username": assigned_user})
            if user_doc:
                patient_email = user_doc.get("email")

        # Photo
        photo_file  = request.files.get("photo")
        photo_path  = None
        photo_filename = None
        if photo_file and photo_file.filename:
            ext = photo_file.filename.rsplit(".", 1)[-1].lower()
            if ext not in allowed_ext:
                flash("Invalid photo format.", "danger")
                return render_template("doctor/register_patient.html", doctors=doctors, patient_users=patient_users)
            photo_filename = f"{patient_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
            photo_path     = os.path.join(upload_dir, photo_filename)
            photo_file.save(photo_path)

        # Feature extraction
        def _int(key, default=0):   return int(request.form.get(key, default) or default)
        def _float(key, default=0): return float(request.form.get(key, default) or default)
        def _str(key, default=""):  return str(request.form.get(key, default) or default)

        features = {
            "Patient_ID":                   patient_id,
            "Age":                          _int("age"),
            "Gender":                       _str("gender", "Male"),
            "Length_of_Hospital_Stay":      _int("length_of_hospital_stay"),
            "ICU_Admission":                _int("icu_admission"),
            "Previous_Hospitalization":     _int("previous_hospitalization"),
            "Previous_MDR_Infection":       _int("previous_mdr_infection"),
            "Antibiotic_Use_Last_90_Days":  _int("antibiotic_use_last_90_days"),
            "Number_of_Antibiotics_Used":   _int("number_of_antibiotics_used"),
            "Duration_of_Antibiotic_Use":   _int("duration_of_antibiotic_use"),
            "Recent_Surgery":               _int("recent_surgery"),
            "Chronic_Disease":              _int("chronic_disease"),
            "Diabetes":                     _int("diabetes"),
            "Kidney_Disease":               _int("kidney_disease"),
            "Immunocompromised":            _int("immunocompromised"),
            "Mechanical_Ventilation":       _int("mechanical_ventilation"),
            "Catheter_Use":                 _int("catheter_use"),
            "Infection_Type":               _str("infection_type", "Bloodstream"),
            "Pathogen_Type":                _str("pathogen_type", "MRSA"),
            "White_Blood_Cell_Count":       _float("white_blood_cell_count", 7.0),
            "C_Reactive_Protein":           _float("c_reactive_protein", 5.0),
            "Fever":                        _int("fever"),
            "Culture_Test_Positive":        _int("culture_test_positive"),
            "Prior_Antibiotic_Failure":     _int("prior_antibiotic_failure"),
            "Ward_Type":                    _str("ward_type", "General"),
            "Contact_With_MDR_Patient":     _int("contact_with_mdr_patient"),
        }

        # Face embedding
        embedding = None
        if photo_path and os.path.exists(photo_path):
            embedding = generate_face_embedding(photo_path)
            if not embedding:
                flash("⚠️ No face detected in photo. Patient registered without face recognition.", "warning")

        # MDR Prediction
        try:
            predictor = MDRPredictor(model_dir=current_app.config["MODEL_DIR"])
            result    = predictor.predict(features)
            pred_dict = {
                "patient_id":               patient_id,
                "assigned_doctor":          assigned_doctor,
                "mdr_probability":          result.mdr_probability,
                "risk_classification":      result.risk_classification,
                "risk_score_pct":           result.risk_score_pct,
                "model_used":               result.model_used,
                "isolation_recommended":    result.isolation_recommended,
                "culture_test_recommended": result.culture_test_recommended,
                "follow_up_days":           result.follow_up_days,
                "clinical_suggestions":     result.clinical_suggestions,
                "alert_level":              result.alert_level,
                "top_risk_factors":         result.top_risk_factors,
                "created_at":               datetime.now()
            }
            mongo.db.predictions.insert_one(pred_dict)

            # Create alert if needed
            if result.alert_level in ("WARNING", "CRITICAL"):
                mongo.db.alerts.insert_one({
                    "patient_id":      patient_id,
                    "patient_name":    name,
                    "assigned_doctor": assigned_doctor,
                    "alert_level":     result.alert_level,
                    "message":         f"Patient {name} ({patient_id}) — {result.risk_classification} MDR Risk ({result.risk_score_pct:.1f}%)",
                    "status":          "active",
                    "created_at":      datetime.now()
                })
                # Send real-time Gmail alert
                try:
                    from utils.email_utils import send_high_risk_registration_alert
                    send_high_risk_registration_alert(
                        patient_id=patient_id,
                        name=name,
                        risk_classification=result.risk_classification,
                        risk_score_pct=result.risk_score_pct,
                        assigned_doctor_username=assigned_doctor
                    )
                except Exception as mail_err:
                    logger.error(f"Failed to trigger registration mail alert: {mail_err}")
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            result = None
            pred_dict = {}
            flash("Prediction model error. Patient registered without prediction.", "warning")

        # Save patient
        mdr_status = 1 if (result and result.mdr_probability >= 0.5) else 0
        patient_doc = {
            "patient_id":         patient_id,
            "name":               name,
            "age":                features["Age"],
            "gender":             features["Gender"],
            "ward_type":          features["Ward_Type"],
            "infection_type":     features["Infection_Type"],
            "pathogen_type":      features["Pathogen_Type"],
            "length_of_hospital_stay": features["Length_of_Hospital_Stay"],
            "icu_admission":      features["ICU_Admission"],
            "mdr_status":         mdr_status,
            "photo_filename":     photo_filename,
            "photo_path":         photo_path,
            "face_embedding":     embedding,
            "assigned_doctor":    assigned_doctor,
            "assigned_user":      assigned_user,
            "patient_email":      patient_email,
            "features":           features,
            "registration_date":  datetime.now(),
        }
        mongo.db.patients.insert_one(patient_doc)

        # Store embedding in embeddings collection for fast lookup
        if embedding:
            mongo.db.face_embeddings.update_one(
                {"patient_id": patient_id},
                {"$set": {
                    "patient_id":   patient_id,
                    "name":         name,
                    "embedding":    embedding,
                    "mdr_status":   mdr_status,
                    "mdr_probability": result.mdr_probability if result else 0,
                    "risk_level":   result.risk_classification if result else "Low",
                    "updated_at":   datetime.now()
                }},
                upsert=True
            )

        flash(f"Patient {name} registered successfully! MDR Risk: {pred_dict.get('risk_classification','N/A')}", "success")
        return redirect(url_for("doctor.patient_detail", patient_id=patient_id))

    return render_template("doctor/register_patient.html", doctors=doctors, patient_users=patient_users)


# ── Patient Detail ─────────────────────────────────────────────────────────────

@doctor_bp.route("/patients/<patient_id>")
@login_required
@doctor_required
def patient_detail(patient_id):
    patient    = mongo.db.patients.find_one({"patient_id": patient_id})
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for("doctor.my_patients"))
    prediction = mongo.db.predictions.find_one({"patient_id": patient_id},
                                                sort=[("created_at", -1)])
    contacts   = list(mongo.db.contacts.find(
        {"$or": [{"person1_id": patient_id}, {"person2_id": patient_id}]}
    ).sort("start_time", -1).limit(20))
    reports    = list(mongo.db.reports.find({"patient_id": patient_id}).sort("created_at", -1))
    return render_template("doctor/patient_detail.html",
                           patient=patient, prediction=prediction,
                           contacts=contacts, reports=reports)


@doctor_bp.route("/my-patients")
@login_required
@doctor_required
def my_patients():
    patients_list = list(mongo.db.patients.find({}).sort("registration_date", -1))
    return render_template("doctor/my_patients.html", patients=patients_list)


@doctor_bp.route("/contacts")
@login_required
@doctor_required
def contacts():
    contacts_list = list(mongo.db.contacts.find().sort("start_time", -1).limit(200))
    return render_template("doctor/contacts.html", contacts=contacts_list)



# ── Webcam / Video Analysis ────────────────────────────────────────────────────

@doctor_bp.route("/monitoring")
@login_required
@doctor_required
def monitoring():
    recent_events = list(mongo.db.contacts.find({"status": "completed"}).sort("start_time", -1).limit(10))
    return render_template("doctor/monitoring.html", recent_events=recent_events)


@doctor_bp.route("/api/process-frame", methods=["POST"])
@login_required
@doctor_required
def process_frame():
    """
    Process a base64-encoded webcam frame.
    Returns detected persons with recognition results.
    """
    try:
        _contact_tracker.distance_threshold = current_app.config.get("CONTACT_DISTANCE_THRESHOLD", 150)
        _contact_tracker.duration_threshold = current_app.config.get("CONTACT_DURATION_THRESHOLD", 3)
        data  = request.get_json(force=True)
        img_b64 = data.get("frame", "")
        if not img_b64:
            return jsonify({"error": "No frame"}), 400

        # Decode
        img_bytes = base64.b64decode(img_b64.split(",")[-1] if "," in img_b64 else img_b64)
        nparr  = np.frombuffer(img_bytes, np.uint8)
        frame  = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Frame decode failed"}), 400

        # Detect faces
        locations = detect_faces_in_frame(frame)
        if not locations:
            return jsonify({"persons": [], "contacts": [], "annotated_frame": frame_to_base64(frame)})

        # Get encodings
        encodings = get_face_encodings_from_frame(frame, locations)

        # Load all known embeddings
        known = list(mongo.db.face_embeddings.find({}, {"_id": 0}))

        detected_persons = []
        annotated = frame.copy()
        now = datetime.now()

        for i, (loc, enc) in enumerate(zip(locations, encodings)):
            match = match_face(enc, known, tolerance=current_app.config["FACE_RECOGNITION_TOLERANCE"])
            top, right, bottom, left = loc

            if match["matched"]:
                pid   = match["patient_id"]
                pname = match.get("patient_name", "Unknown")
                mdr   = match.get("mdr_status", 0)
                prob  = match.get("mdr_probability", 0)
                risk  = match.get("risk_level", "Low")
                conf  = match["confidence"]
                color = (0, 0, 255) if mdr else (0, 200, 0)
                label = f"{pname} [MDR]" if mdr else pname

                # Save detected face
                frame_dir = current_app.config["UPLOAD_FOLDER_FRAMES"]
                saved_frame = save_detected_face(frame, loc, frame_dir, pid)

                # Update last seen
                mongo.db.patients.update_one(
                    {"patient_id": pid},
                    {"$set": {"last_seen": now, "last_frame": saved_frame}}
                )

                detected_persons.append({
                    "patient_id":      pid,
                    "name":            pname,
                    "location":        list(loc),
                    "mdr_status":      mdr,
                    "mdr_probability": prob,
                    "risk_level":      risk,
                    "confidence":      conf,
                    "saved_frame":     saved_frame
                })
            else:
                color = (128, 128, 128)
                label = f"Unknown"
                conf  = 0
                detected_persons.append({
                    "patient_id":      f"UNKNOWN_{i}",
                    "name":            "Unknown",
                    "location":        list(loc),
                    "mdr_status":      0,
                    "mdr_probability": 0,
                    "risk_level":      "Unknown",
                    "confidence":      0
                })

            draw_recognition_box(annotated, loc, label, color, conf)

        # Contact tracing update
        completed_contacts = _contact_tracker.update(
            detected_persons,
            now
        )
        active_contacts = _contact_tracker.get_active_contacts()

        # Save face image of unknown persons with their stable ID
        frame_dir = current_app.config["UPLOAD_FOLDER_FRAMES"]
        for p in detected_persons:
            pid = p["patient_id"]
            if pid.startswith("UNKNOWN_TRACK"):
                saved_frame = save_detected_face(frame, tuple(p["location"]), frame_dir, pid)
                p["saved_frame"] = saved_frame
                # Update active contacts
                for key, c in _contact_tracker.active_contacts.items():
                    if c["person1_id"] == pid or c["person2_id"] == pid:
                        c["saved_frame"] = saved_frame
                # Update completed contacts
                for c in completed_contacts:
                    if c["person1_id"] == pid or c["person2_id"] == pid:
                        c["saved_frame"] = saved_frame

        # Save completed contacts
        new_alerts = []
        for c in completed_contacts:
            contact_doc = {
                "person1_id":    c["person1_id"],
                "person1_name":  c["person1_name"],
                "person2_id":    c["person2_id"],
                "person2_name":  c["person2_name"],
                "start_time":    c["start_time"],
                "duration":      c["duration"],
                "exposure_score":c.get("exposure_score", 0),
                "exposure_risk": c.get("exposure_risk", "Low"),
                "avg_proximity": c.get("avg_proximity", 0),
                "saved_frame":   c.get("saved_frame"),
                "status":        "completed",
                "created_at":    now
            }
            mongo.db.contacts.insert_one(contact_doc)

            # If risk is Medium or High, generate report automatically
            exposure_risk = c.get("exposure_risk", "Low")
            if exposure_risk in ("Medium", "High"):
                patient_id = c["person1_id"] if not c["person1_id"].startswith("UNKNOWN") else c["person2_id"]
                patient = mongo.db.patients.find_one({"patient_id": patient_id})
                if patient:
                    prediction = mongo.db.predictions.find_one({"patient_id": patient_id}, sort=[("created_at", -1)])
                    if prediction:
                        # Get recent completed contacts for this patient
                        patient_contacts = list(mongo.db.contacts.find(
                            {"$or": [{"person1_id": patient_id}, {"person2_id": patient_id}]}
                        ).sort("start_time", -1).limit(20))
                        
                        # Unknown person's face path
                        unknown_face_path = None
                        if c.get("saved_frame"):
                            unknown_face_path = os.path.join(current_app.config["UPLOAD_FOLDER_FRAMES"], c["saved_frame"])
                            
                        # Generate the PDF report
                        reports_folder = current_app.config.get("REPORTS_FOLDER") or os.path.join(current_app.root_path, "uploads", "reports")
                        photo_path = patient.get("photo_path")
                        
                        try:
                            filepath, filename, report_id = generate_patient_report(
                                patient=patient,
                                prediction=prediction,
                                contacts=patient_contacts,
                                reports_folder=reports_folder,
                                patient_photo_path=photo_path,
                                detected_face_path=unknown_face_path
                            )
                            
                            # Identify the contact target (person contacted)
                            contact_person_id = c["person2_id"] if c["person1_id"] == patient_id else c["person1_id"]
                            contact_person_name = c["person2_name"] if c["person1_id"] == patient_id else c["person1_name"]
                            
                            # Insert report document
                            mongo.db.reports.insert_one({
                                "report_id":           report_id,
                                "patient_id":          patient_id,
                                "patient_name":        patient.get("name", ""),
                                "filename":            filename,
                                "filepath":            filepath,
                                "generated_by":        current_user.username if (current_user and current_user.is_authenticated) else "system",
                                "created_at":          datetime.now(),
                                "report_type":         "Exposure Report",
                                "contact_person_id":   contact_person_id,
                                "contact_person_name": contact_person_name
                            })
                            logger.info(f"Auto-generated PDF report for patient {patient_id} due to {exposure_risk}-risk contact: {filename}")
                        except Exception as rep_err:
                            logger.error(f"Auto report generation failed: {rep_err}")

            # Alert if exposure contact completed
            alert_level = "CRITICAL" if c.get("exposure_risk") == "High" else "WARNING" if c.get("exposure_risk") == "Medium" else "INFO"
            
            # Find assigned doctor for this patient
            patient_id = c["person1_id"] if not c["person1_id"].startswith("UNKNOWN") else c["person2_id"]
            assigned_doc = current_user.username
            if not patient_id.startswith("UNKNOWN"):
                p_record = mongo.db.patients.find_one({"patient_id": patient_id})
                if p_record and p_record.get("assigned_doctor"):
                    assigned_doc = p_record["assigned_doctor"]

            alert_doc = {
                "patient_id":    c["person1_id"],
                "patient_name":  c["person1_name"],
                "contact_id":    c["person2_id"],
                "contact_name":  c["person2_name"],
                "assigned_doctor": assigned_doc,
                "alert_level":   alert_level,
                "message":       f"{c.get('exposure_risk')}-risk contact: {c['person1_name']} ↔ {c['person2_name']} — {c['duration']:.1f}s, score {c.get('exposure_score',0):.1f}",
                "status":        "active",
                "created_at":    now
            }
            mongo.db.alerts.insert_one(alert_doc)
            
            # Send real-time email alert if exposure risk is Medium or High
            if c.get("exposure_risk") in ("Medium", "High"):
                try:
                    from utils.email_utils import send_contact_exposure_alert
                    send_contact_exposure_alert(
                        contact_details=c,
                        alert_level=alert_level,
                        assigned_doctor_username=assigned_doc
                    )
                except Exception as mail_err:
                    logger.error(f"Failed to trigger contact mail alert: {mail_err}")
            
            # Format for JSON serialization
            alert_doc["_id"] = str(alert_doc["_id"])
            alert_doc["created_at"] = alert_doc["created_at"].strftime("%H:%M:%S")
            new_alerts.append(alert_doc)

        return jsonify({
            "persons":          detected_persons,
            "active_contacts":  active_contacts,
            "completed_contacts": len(completed_contacts),
            "new_alerts":       new_alerts,
            "annotated_frame":  frame_to_base64(annotated)
        })

    except Exception as e:
        logger.error(f"Frame processing error: {e}")
        return jsonify({"error": str(e)}), 500


@doctor_bp.route("/api/generate-report/<patient_id>", methods=["POST"])
@login_required
@doctor_required
def generate_report(patient_id):
    """Generate PDF report for a patient."""
    patient    = mongo.db.patients.find_one({"patient_id": patient_id})
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    prediction = mongo.db.predictions.find_one({"patient_id": patient_id},
                                                sort=[("created_at", -1)])
    if not prediction:
        return jsonify({"error": "No prediction found"}), 404

    contacts   = list(mongo.db.contacts.find(
        {"$or": [{"person1_id": patient_id}, {"person2_id": patient_id}]}
    ).sort("start_time", -1).limit(20))

    # Final assessment
    exposure_scores = [c.get("exposure_score", 0) for c in contacts]
    max_exposure    = max(exposure_scores) if exposure_scores else 0
    final_assessment = compute_final_risk(
        prediction.get("mdr_probability", 0), max_exposure
    )
    prediction["final_assessment"] = final_assessment

    # Paths
    reports_folder = os.path.join(current_app.root_path, "uploads", "reports")
    photo_path     = patient.get("photo_path")
    detected_frame = None
    if patient.get("last_frame"):
        detected_frame = os.path.join(current_app.config["UPLOAD_FOLDER_FRAMES"],
                                       patient["last_frame"])

    try:
        filepath, filename, report_id = generate_patient_report(
            patient=patient,
            prediction=prediction,
            contacts=contacts,
            reports_folder=reports_folder,
            patient_photo_path=photo_path,
            detected_face_path=detected_frame
        )

        mongo.db.reports.insert_one({
            "report_id":       report_id,
            "patient_id":      patient_id,
            "patient_name":    patient.get("name", ""),
            "filename":        filename,
            "filepath":        filepath,
            "generated_by":    current_user.username,
            "created_at":      datetime.now(),
            "report_type":     "Diagnostic Report"
        })

        return jsonify({"success": True, "report_id": report_id, "filename": filename})
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return jsonify({"error": str(e)}), 500


@doctor_bp.route("/reports/download/<report_id>")
@login_required
@doctor_required
def download_report(report_id):
    report = mongo.db.reports.find_one({"report_id": report_id})
    if not report or not os.path.exists(report.get("filepath", "")):
        flash("Report not found.", "danger")
        return redirect(url_for("doctor.my_patients"))
    return send_file(report["filepath"], as_attachment=True,
                     download_name=report.get("filename"))


@doctor_bp.route("/api/active-contacts")
@login_required
@doctor_required
def active_contacts():
    _contact_tracker.distance_threshold = current_app.config.get("CONTACT_DISTANCE_THRESHOLD", 150)
    _contact_tracker.duration_threshold = current_app.config.get("CONTACT_DURATION_THRESHOLD", 3)
    contacts = _contact_tracker.get_active_contacts()
    return jsonify({"contacts": contacts})

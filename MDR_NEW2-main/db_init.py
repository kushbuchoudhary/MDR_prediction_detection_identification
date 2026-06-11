"""
db_init.py — Initialize MongoDB indexes and seed default admin account.
Run once before starting the application.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pymongo import MongoClient, ASCENDING, DESCENDING
from flask_bcrypt import generate_password_hash
from datetime import datetime
import getpass

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/mdr_disease_db")


def init_db():
    client = MongoClient(MONGO_URI)
    db     = client["mdr_disease_db"]

    print("✅ Connected to MongoDB")

    # ── Indexes ────────────────────────────────────────────────────────────────
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.patients.create_index([("patient_id", ASCENDING)], unique=True)
    db.patients.create_index([("assigned_doctor", ASCENDING)])
    db.patients.create_index([("mdr_status", ASCENDING)])
    db.predictions.create_index([("patient_id", ASCENDING)])
    db.predictions.create_index([("created_at", DESCENDING)])
    db.face_embeddings.create_index([("patient_id", ASCENDING)], unique=True)
    db.contacts.create_index([("person1_id", ASCENDING)])
    db.contacts.create_index([("person2_id", ASCENDING)])
    db.contacts.create_index([("start_time", DESCENDING)])
    db.alerts.create_index([("patient_id", ASCENDING)])
    db.alerts.create_index([("status", ASCENDING)])
    db.alerts.create_index([("created_at", DESCENDING)])
    db.reports.create_index([("patient_id", ASCENDING)])
    db.reports.create_index([("report_id", ASCENDING)], unique=True)

    print("✅ Indexes created")

    # ── Seed admin account ─────────────────────────────────────────────────────
    if db.users.find_one({"role": "admin"}):
        print("ℹ️  Admin account already exists. Skipping seed.")
    else:
        print("\n── Create Default Admin Account ──")
        name     = input("Admin full name [System Admin]: ").strip() or "System Admin"
        username = input("Admin username [admin]: ").strip() or "admin"
        email    = input("Admin email [admin@mdr.local]: ").strip() or "admin@mdr.local"
        password = getpass.getpass("Admin password [Admin@123]: ") or "Admin@123"

        hashed = generate_password_hash(password).decode("utf-8")
        db.users.insert_one({
            "name":       name,
            "username":   username,
            "email":      email,
            "password":   hashed,
            "role":       "admin",
            "is_active":  True,
            "created_at": datetime.now(),
            "last_login": None
        })
        print(f"✅ Admin account created: {username}")

    # ── Seed default doctor account ────────────────────────────────────────────
    if not db.users.find_one({"role": "doctor"}):
        hashed_doc = generate_password_hash("Doctor@123").decode("utf-8")
        db.users.insert_one({
            "name":       "Dr. Default Doctor",
            "username":   "doctor",
            "email":      "doctor@mdr.local",
            "password":   hashed_doc,
            "role":       "doctor",
            "is_active":  True,
            "created_at": datetime.now(),
            "last_login": None
        })
        print("✅ Default doctor created  — username: doctor | password: Doctor@123")

    # ── Seed default user account ──────────────────────────────────────────────
    if not db.users.find_one({"role": "user", "username": "patient"}):
        hashed_usr = generate_password_hash("User@123").decode("utf-8")
        db.users.insert_one({
            "name":       "Demo Patient",
            "username":   "patient",
            "email":      "patient@mdr.local",
            "password":   hashed_usr,
            "role":       "user",
            "is_active":  True,
            "created_at": datetime.now(),
            "last_login": None
        })
        print("✅ Default patient user created — username: patient | password: User@123")

    print("\n🚀 Database initialisation complete!")
    print("─" * 50)
    print("Default credentials:")
    print("  Admin  : admin       / Admin@123  (or your custom credentials)")
    print("  Doctor : doctor      / Doctor@123")
    print("  Patient: patient     / User@123")
    print("─" * 50)
    client.close()


if __name__ == "__main__":
    init_db()

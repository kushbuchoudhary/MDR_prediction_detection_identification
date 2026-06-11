"""
Authentication Routes: Signup, Login, Logout
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from extensions import mongo, bcrypt
from models.user_model import User
from datetime import datetime
import logging

auth_bp = Blueprint("auth", __name__)
logger  = logging.getLogger(__name__)


@auth_bp.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for(f"{current_user.role}.dashboard"))
    return render_template("shared/landing.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(f"{current_user.role}.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role     = request.form.get("role", "")

        user_doc = mongo.db.users.find_one({"username": username, "role": role})
        if user_doc and bcrypt.check_password_hash(user_doc["password"], password):
            if not user_doc.get("is_active", True):
                flash("Account deactivated. Contact administrator.", "danger")
                return render_template("auth/login.html")
            user = User(user_doc)
            login_user(user, remember=True)
            mongo.db.users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"last_login": datetime.now()}}
            )
            logger.info(f"User {username} ({role}) logged in.")
            next_page = request.args.get("next")
            if next_page:
                return redirect(next_page)
            return redirect(url_for(f"{role}.dashboard"))
        else:
            flash("Invalid username, password, or role.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for(f"{current_user.role}.dashboard"))

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        role     = request.form.get("role", "user")

        # Validation
        if not all([name, username, email, password]):
            flash("All fields are required.", "danger")
            return render_template("auth/signup.html")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/signup.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("auth/signup.html")
        if mongo.db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            flash("Username or email already exists.", "danger")
            return render_template("auth/signup.html")
        if role not in ("admin", "doctor", "user"):
            flash("Invalid role.", "danger")
            return render_template("auth/signup.html")

        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        mongo.db.users.insert_one({
            "name":        name,
            "username":    username,
            "email":       email,
            "password":    hashed_pw,
            "role":        role,
            "is_active":   True,
            "created_at":  datetime.now(),
            "last_login":  None
        })
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/signup.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logger.info(f"User {current_user.username} logged out.")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.landing"))

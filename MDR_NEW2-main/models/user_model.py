"""
User Model for Flask-Login
"""

from flask_login import UserMixin
from extensions import mongo, login_manager
from bson import ObjectId


class User(UserMixin):
    def __init__(self, user_doc):
        self.id       = str(user_doc["_id"])
        self.username = user_doc["username"]
        self.email    = user_doc["email"]
        self.role     = user_doc["role"]          # admin | doctor | user
        self.name     = user_doc.get("name", "")
        self.is_active_flag = user_doc.get("is_active", True)

    def get_id(self):
        return self.id

    @property
    def is_active(self):
        return self.is_active_flag

    def is_admin(self):
        return self.role == "admin"

    def is_doctor(self):
        return self.role == "doctor"

    def is_user(self):
        return self.role == "user"


@login_manager.user_loader
def load_user(user_id):
    try:
        doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if doc:
            return User(doc)
    except Exception:
        pass
    return None

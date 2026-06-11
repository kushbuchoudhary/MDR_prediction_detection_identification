"""
Contact Tracing & Exposure Risk Calculation
"""

import math
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def calculate_proximity(loc1: tuple, loc2: tuple) -> float:
    """
    Calculate pixel distance between centers of two face bounding boxes.
    loc = (top, right, bottom, left)
    """
    def center(loc):
        top, right, bottom, left = loc
        return ((left + right) / 2, (top + bottom) / 2)

    cx1, cy1 = center(loc1)
    cx2, cy2 = center(loc2)
    return math.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)


def is_in_contact(loc1: tuple, loc2: tuple, threshold: int = 150) -> bool:
    """Return True if two faces are within threshold pixels of each other."""
    return calculate_proximity(loc1, loc2) <= threshold


def calculate_exposure_score(
    duration_seconds: float,
    mdr_probability: float,
    proximity_score: float,         # 0–1, higher = closer
    mdr_status: int = 1             # 1 = MDR positive source
) -> float:
    """
    Exposure score formula:
      score = (duration_factor * 40) + (mdr_risk_factor * 35) + (proximity_factor * 25)
    Returns 0–100.
    """
    if mdr_status == 0:
        return 0.0

    # Duration factor: log scale, maxes at ~1 for 3600s (1 hour)
    duration_factor  = min(1.0, math.log1p(duration_seconds) / math.log1p(3600))

    mdr_risk_factor  = min(1.0, mdr_probability)
    proximity_factor = min(1.0, proximity_score)

    score = (duration_factor * 40) + (mdr_risk_factor * 35) + (proximity_factor * 25)
    return round(score, 2)


def classify_exposure_risk(exposure_score: float) -> str:
    if exposure_score >= 53:
        return "High"
    elif exposure_score >= 25:
        return "Medium"
    return "Low"


def compute_final_risk(mdr_probability: float, exposure_score: float) -> dict:
    """
    Combine XGBoost MDR probability with exposure score for final risk.
    """
    # Normalize exposure to 0–1
    norm_exposure = exposure_score / 100.0
    # Weighted combination
    final_score = (mdr_probability * 0.6) + (norm_exposure * 0.4)
    final_score = min(1.0, final_score)

    if final_score >= 0.65:
        classification = "High"
        color          = "#dc3545"
        alert          = "CRITICAL"
    elif final_score >= 0.35:
        classification = "Medium"
        color          = "#ffc107"
        alert          = "WARNING"
    else:
        classification = "Low"
        color          = "#28a745"
        alert          = "INFO"

    return {
        "final_score":      round(final_score * 100, 1),
        "classification":   classification,
        "color":            color,
        "alert":            alert,
        "mdr_contribution": round(mdr_probability * 60, 1),
        "exposure_contribution": round(norm_exposure * 40, 1)
    }


def generate_recommendations(final_classification: str, exposure_score: float,
                              mdr_prob: float, isolation_recommended: bool) -> List[str]:
    """Generate actionable recommendations based on risk level."""
    recs = []

    if final_classification == "High":
        recs.extend([
            "⚠️ Immediate isolation required — notify infection control team NOW.",
            "🧪 Order broad-spectrum culture panel (blood, urine, wound).",
            "😷 Enforce strict PPE: gown, gloves, N95 mask for all contacts.",
            "🏥 Transfer to single-room isolation unit if available.",
            "📋 Screen all close contacts within 24 hours.",
            "💊 Review and de-escalate antibiotic regimen after culture results.",
            "📞 Notify attending physician and department head immediately."
        ])
    elif final_classification == "Medium":
        recs.extend([
            "🔍 Collect culture specimens before the next antibiotic dose.",
            "🧼 Enhanced hand-hygiene protocol for all attending staff.",
            "📊 Daily reassessment of MDR risk factors recommended.",
            "💊 Consider antibiotic stewardship review.",
            "🩸 Monitor WBC and CRP every 48 hours.",
            "😷 Standard contact precautions (gloves and gown)."
        ])
    else:
        recs.extend([
            "✅ Routine infection-control precautions sufficient.",
            "💊 Continue standard antibiotic protocol.",
            "📋 Reassess risk if clinical status changes.",
            "🧼 Standard hand hygiene compliance required."
        ])

    if exposure_score >= 60:
        recs.append("🚨 High exposure detected — initiate post-exposure prophylaxis assessment.")
    if isolation_recommended:
        recs.append("🏥 Patient isolation is strongly recommended based on MDR probability.")

    return recs


class ContactTracker:
    """
    Tracks ongoing contacts between identified persons across frames.
    Maintains a buffer of active contacts and persists completed ones.
    """

    def __init__(self, distance_threshold=150, duration_threshold=3):
        self.distance_threshold = distance_threshold
        self.duration_threshold = duration_threshold
        self.active_contacts: Dict[str, dict] = {}   # key: "pid1_pid2"
        self.tracked_unknowns = {}                   # key: track_id -> {"location": loc, "last_seen": datetime}
        self.next_unknown_id = 0

    def _contact_key(self, pid1: str, pid2: str) -> str:
        return "_".join(sorted([pid1, pid2]))

    def update(self, detected_persons: List[dict], frame_time: datetime) -> List[dict]:
        """
        Update contact tracker with currently detected persons.
        detected_persons: list of {patient_id, name, location, mdr_status, mdr_probability, risk_level}
        Returns list of NEW completed contacts.
        """
        completed = []
        seen_keys = set()

        # Track unknown persons to keep their IDs consistent
        unknown_detections = []
        for p in detected_persons:
            pid = p.get("patient_id", "")
            pname = p.get("name", "")
            if pid.startswith("UNKNOWN") or pname == "Unknown":
                unknown_detections.append(p)

        # Clean up old tracked unknowns (not seen for > 12.0 seconds)
        expired_tracks = []
        for track_id, info in list(self.tracked_unknowns.items()):
            if (frame_time - info["last_seen"]).total_seconds() > 12.0:
                expired_tracks.append(track_id)
        for track_id in expired_tracks:
            self.tracked_unknowns.pop(track_id)

        def get_center(loc):
            return ((loc[3] + loc[1]) / 2.0, (loc[0] + loc[2]) / 2.0)

        # Match current detections to tracked unknowns using greedy distance matching
        available_tracks = list(self.tracked_unknowns.keys())
        assignments = {}

        pairs = []
        for d_idx, det in enumerate(unknown_detections):
            det_center = get_center(det["location"])
            for track_id in available_tracks:
                info = self.tracked_unknowns[track_id]
                track_center = get_center(info["location"])
                dist = math.sqrt((det_center[0] - track_center[0])**2 + (det_center[1] - track_center[1])**2)
                if dist < 150: # Match threshold in pixels
                    pairs.append((dist, d_idx, track_id))

        # Sort pairs by distance
        pairs.sort(key=lambda x: x[0])

        used_detections = set()
        used_tracks = set()
        for dist, d_idx, track_id in pairs:
            if d_idx not in used_detections and track_id not in used_tracks:
                assignments[d_idx] = track_id
                used_detections.add(d_idx)
                used_tracks.add(track_id)

        # Update existing tracks
        for d_idx, track_id in assignments.items():
            det = unknown_detections[d_idx]
            self.tracked_unknowns[track_id]["location"] = det["location"]
            self.tracked_unknowns[track_id]["last_seen"] = frame_time
            det["patient_id"] = track_id

        # Create new tracks for unmatched detections
        for d_idx, det in enumerate(unknown_detections):
            if d_idx not in used_detections:
                new_track_id = f"UNKNOWN_TRACK_{self.next_unknown_id}"
                self.next_unknown_id += 1
                self.tracked_unknowns[new_track_id] = {
                    "location": det["location"],
                    "last_seen": frame_time
                }
                det["patient_id"] = new_track_id

        # Check all pairs
        for i in range(len(detected_persons)):
            for j in range(i + 1, len(detected_persons)):
                p1 = detected_persons[i]
                p2 = detected_persons[j]

                if p1["patient_id"] == p2["patient_id"]:
                    continue

                # At least one must be MDR positive for contact tracing
                if p1.get("mdr_status", 0) == 0 and p2.get("mdr_status", 0) == 0:
                    continue

                dist = calculate_proximity(p1["location"], p2["location"])
                if dist > self.distance_threshold:
                    continue

                key = self._contact_key(p1["patient_id"], p2["patient_id"])
                seen_keys.add(key)
                proximity_score = max(0, 1 - dist / self.distance_threshold)

                if key not in self.active_contacts:
                    self.active_contacts[key] = {
                        "person1_id":   p1["patient_id"],
                        "person1_name": p1.get("name", "Unknown"),
                        "person2_id":   p2["patient_id"],
                        "person2_name": p2.get("name", "Unknown"),
                        "start_time":   frame_time,
                        "last_seen":    frame_time,
                        "duration":     0,
                        "proximity_scores": [proximity_score],
                        "mdr_source_prob": max(
                            p1.get("mdr_probability", 0) if p1.get("mdr_status") else 0,
                            p2.get("mdr_probability", 0) if p2.get("mdr_status") else 0
                        )
                    }
                else:
                    c = self.active_contacts[key]
                    c["last_seen"] = frame_time
                    c["duration"]  = (frame_time - c["start_time"]).total_seconds()
                    c["proximity_scores"].append(proximity_score)

        # Check for ended contacts (exceeded grace period of 10 seconds)
        ended_keys = []
        grace_seconds = 10.0
        for key, c in list(self.active_contacts.items()):
            if key not in seen_keys:
                time_since_seen = (frame_time - c["last_seen"]).total_seconds()
                if time_since_seen > grace_seconds:
                    ended_keys.append(key)

        for key in ended_keys:
            c = self.active_contacts.pop(key)
            if c["duration"] >= self.duration_threshold:
                avg_prox = sum(c["proximity_scores"]) / len(c["proximity_scores"]) if c["proximity_scores"] else 0.0
                exp_score = calculate_exposure_score(
                    c["duration"], c["mdr_source_prob"], avg_prox
                )
                c["exposure_score"] = exp_score
                c["exposure_risk"]  = classify_exposure_risk(exp_score)
                c["avg_proximity"]  = round(avg_prox, 3)
                completed.append(c)

        return completed

    def get_active_contacts(self) -> List[dict]:
        """Return current active contacts with durations, calculated exposure scores, and risk."""
        now = datetime.now()
        result = []
        for key, c in self.active_contacts.items():
            duration = (now - c["start_time"]).total_seconds()
            avg_prox = sum(c["proximity_scores"]) / len(c["proximity_scores"]) if c["proximity_scores"] else 0.0
            exp_score = calculate_exposure_score(
                duration, c["mdr_source_prob"], avg_prox
            )
            exposure_risk = classify_exposure_risk(exp_score)
            result.append({
                **c,
                "duration": duration,
                "exposure_score": exp_score,
                "exposure_risk": exposure_risk,
                "avg_proximity": round(avg_prox, 3)
            })
        return result

#!/usr/bin/env python3
"""
MDR Risk Prediction Module
===========================
Drop-in integration for the MDR Surveillance Workflow (Steps 3–5).

Usage:
    from mdr_predictor import MDRPredictor

    predictor = MDRPredictor(model_dir="mdr_model")
    result = predictor.predict(patient_data)
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class MDRPredictionResult:
    """Structured output consumed by downstream workflow steps."""
    patient_id: str
    mdr_probability: float          # 0.0 – 1.0
    risk_classification: str        # Low / Medium / High
    risk_score_pct: float           # 0 – 100 (display-friendly)
    model_used: str

    # Step 5 – Treatment Insight Generation
    isolation_recommended: bool
    culture_test_recommended: bool
    follow_up_days: int
    clinical_suggestions: list
    alert_level: str                # INFO / WARNING / CRITICAL

    # For audit / explainability
    top_risk_factors: list
    raw_features_used: dict


class MDRPredictor:
    """
    Loads trained RF and XGBoost models and exposes a unified predict() interface.

    Parameters
    ----------
    model_dir : str
        Directory containing rf_model.joblib, xgb_model.joblib,
        label_encoders.joblib, and metrics.json
    preferred_model : str
        "xgboost" (default – winner) or "random_forest"
    """

    RISK_THRESHOLDS = {"low": (0.0, 0.40), "medium": (0.40, 0.70), "high": (0.70, 1.01)}

    FEATURE_COLUMNS = [
        "Age", "Gender", "Length_of_Hospital_Stay", "ICU_Admission",
        "Previous_Hospitalization", "Previous_MDR_Infection",
        "Antibiotic_Use_Last_90_Days", "Number_of_Antibiotics_Used",
        "Duration_of_Antibiotic_Use", "Recent_Surgery", "Chronic_Disease",
        "Diabetes", "Kidney_Disease", "Immunocompromised",
        "Mechanical_Ventilation", "Catheter_Use", "Infection_Type",
        "Pathogen_Type", "White_Blood_Cell_Count", "C_Reactive_Protein",
        "Fever", "Culture_Test_Positive", "Prior_Antibiotic_Failure",
        "Ward_Type", "Contact_With_MDR_Patient"
    ]

    CATEGORICAL_COLUMNS = ["Gender", "Infection_Type", "Pathogen_Type", "Ward_Type"]

    # Clinical logic for Step 5 insights
    CLINICAL_RULES = {
        "high": [
            "Initiate immediate contact precautions (gown + gloves + mask).",
            "Notify infection control team within 1 hour.",
            "Order broad-spectrum culture panel (blood, urine, wound).",
            "Review and de-escalate antibiotic regimen after culture results.",
            "Place patient in single-room isolation if available.",
            "Screen close contacts within 24 hours."
        ],
        "medium": [
            "Collect culture specimens before next antibiotic dose.",
            "Enhanced hand-hygiene protocol for attending staff.",
            "Daily reassessment of MDR risk factors.",
            "Consider antibiotic stewardship review.",
            "Monitor WBC and CRP every 48 hours."
        ],
        "low": [
            "Routine infection-control precautions.",
            "Continue standard antibiotic protocol.",
            "Reassess risk if clinical status changes."
        ]
    }

    def __init__(self, model_dir: str = "mdr_model", preferred_model: str = "xgboost"):
        self.model_dir = model_dir
        self.preferred_model = preferred_model.lower()
        self._load_artifacts()

    def _load_artifacts(self):
        rf_path  = os.path.join(self.model_dir, "rf_model.joblib")
        xgb_path = os.path.join(self.model_dir, "xgb_model.joblib")
        le_path  = os.path.join(self.model_dir, "label_encoders.joblib")
        metrics_path = os.path.join(self.model_dir, "metrics.json")

        self.rf_model  = joblib.load(rf_path)
        self.xgb_model = joblib.load(xgb_path)
        self.le_dict   = joblib.load(le_path)

        with open(metrics_path) as f:
            self.metrics = json.load(f)

        self._active_model = self.xgb_model if self.preferred_model == "xgboost" else self.rf_model
        self._active_name  = "XGBoost" if self.preferred_model == "xgboost" else "RandomForest"
        print(f"[MDRPredictor] Loaded. Active model: {self._active_name}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, patient_data: dict) -> MDRPredictionResult:
        """
        Predict MDR risk for a single patient.

        Parameters
        ----------
        patient_data : dict
            Keys must include all FEATURE_COLUMNS.
            Patient_ID is optional (defaults to "UNKNOWN").

        Returns
        -------
        MDRPredictionResult dataclass (JSON-serialisable via asdict())
        """
        patient_id = patient_data.get("Patient_ID", "UNKNOWN")
        X = self._preprocess(patient_data)
        prob = float(self._active_model.predict_proba(X)[0, 1])
        risk_cls = self._classify_risk(prob)
        insights = self._generate_insights(prob, risk_cls, patient_data)
        top_factors = self._top_risk_factors(X)

        return MDRPredictionResult(
            patient_id=patient_id,
            mdr_probability=round(prob, 4),
            risk_classification=risk_cls,
            risk_score_pct=round(prob * 100, 1),
            model_used=self._active_name,
            isolation_recommended=insights["isolation_recommended"],
            culture_test_recommended=insights["culture_test_recommended"],
            follow_up_days=insights["follow_up_days"],
            clinical_suggestions=insights["clinical_suggestions"],
            alert_level=insights["alert_level"],
            top_risk_factors=top_factors,
            raw_features_used={k: patient_data.get(k) for k in self.FEATURE_COLUMNS}
        )

    def predict_batch(self, patients: list) -> list:
        """Predict for a list of patient dicts. Returns list of MDRPredictionResult."""
        return [self.predict(p) for p in patients]

    def predict_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict for a DataFrame. Appends prediction columns."""
        results = self.predict_batch(df.to_dict(orient="records"))
        out = df.copy()
        out["mdr_probability"]     = [r.mdr_probability     for r in results]
        out["risk_classification"] = [r.risk_classification for r in results]
        out["risk_score_pct"]      = [r.risk_score_pct      for r in results]
        out["alert_level"]         = [r.alert_level         for r in results]
        return out

    def compare_models(self, patient_data: dict) -> dict:
        """Run both models and return a side-by-side comparison dict."""
        X = self._preprocess(patient_data)
        rf_prob  = float(self.rf_model.predict_proba(X)[0, 1])
        xgb_prob = float(self.xgb_model.predict_proba(X)[0, 1])
        return {
            "patient_id": patient_data.get("Patient_ID", "UNKNOWN"),
            "random_forest": {
                "probability": round(rf_prob, 4),
                "risk": self._classify_risk(rf_prob),
                "score_pct": round(rf_prob * 100, 1),
                "cv_auc": self.metrics["random_forest"]["cv_auc_mean"]
            },
            "xgboost": {
                "probability": round(xgb_prob, 4),
                "risk": self._classify_risk(xgb_prob),
                "score_pct": round(xgb_prob * 100, 1),
                "cv_auc": self.metrics["xgboost"]["cv_auc_mean"]
            },
            "recommended_model": self.metrics["winner"]
        }

    def get_model_metrics(self) -> dict:
        """Return training metrics for both models."""
        return self.metrics

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _preprocess(self, patient_data: dict) -> pd.DataFrame:
        row = {col: patient_data.get(col, 0) for col in self.FEATURE_COLUMNS}
        df = pd.DataFrame([row])
        for col in self.CATEGORICAL_COLUMNS:
            le = self.le_dict[col]
            val = str(df[col].iloc[0])
            if val not in le.classes_:
                val = le.classes_[0]  # fallback to first known class
            df[col] = le.transform([val])
        return df[self.FEATURE_COLUMNS]

    def _classify_risk(self, prob: float) -> str:
        for label, (lo, hi) in self.RISK_THRESHOLDS.items():
            if lo <= prob < hi:
                return label.capitalize()
        return "High"

    def _generate_insights(self, prob: float, risk_cls: str, data: dict) -> dict:
        key = risk_cls.lower()
        isolation  = prob >= 0.71
        culture    = prob >= 0.41 or data.get("Culture_Test_Positive", 0) == 0
        follow_up  = {"low": 14, "medium": 7, "high": 2}.get(key, 7)
        alert_lvl  = {"low": "INFO", "medium": "WARNING", "high": "CRITICAL"}.get(key, "INFO")
        suggestions = self.CLINICAL_RULES.get(key, [])
        return {
            "isolation_recommended": isolation,
            "culture_test_recommended": culture,
            "follow_up_days": follow_up,
            "clinical_suggestions": suggestions,
            "alert_level": alert_lvl
        }

    def _top_risk_factors(self, X: pd.DataFrame, top_n: int = 5) -> list:
        importances = self._active_model.feature_importances_
        fi = pd.Series(importances, index=self.FEATURE_COLUMNS)
        top = fi.nlargest(top_n)
        return [
            {"feature": feat, "importance": round(float(imp), 4), "value": float(X[feat].iloc[0])}
            for feat, imp in top.items()
        ]

# MDR Risk Prediction Model — Integration Package

## Files
| File | Description |
|------|-------------|
| `mdr_predictor.py` | Main Python module — import this |
| `xgb_model.joblib` | XGBoost model (winner) |
| `rf_model.joblib` | Random Forest model |
| `label_encoders.joblib` | Categorical encoders |
| `metrics.json` | Training/evaluation metrics |

## Quick Start
```python
from mdr_predictor import MDRPredictor

predictor = MDRPredictor(model_dir="mdr_model")
result = predictor.predict(patient_data_dict)

print(result.risk_classification)   # Low / Medium / High
print(result.mdr_probability)        # 0.0 – 1.0
print(result.clinical_suggestions)  # list of strings
```

## Workflow Integration Map

| Workflow Step | Module Call |
|---|---|
| Step 3 – AI-Based MDR Risk Prediction | `predictor.predict(patient_data)` |
| Step 4 – Risk Classification | `result.risk_classification`, `result.risk_score_pct` |
| Step 5 – Treatment Insights | `result.isolation_recommended`, `result.culture_test_recommended`, `result.clinical_suggestions` |
| Step 10 – Alert Generation | `result.alert_level` (INFO / WARNING / CRITICAL) |
| Step 12 – Report Generation | `from dataclasses import asdict; asdict(result)` → JSON |

## Input Schema
```json
{
  "Patient_ID": "P00001",
  "Age": 45,
  "Gender": "Male",
  "Length_of_Hospital_Stay": 10,
  "ICU_Admission": 1,
  "Previous_Hospitalization": 1,
  "Previous_MDR_Infection": 0,
  "Antibiotic_Use_Last_90_Days": 1,
  "Number_of_Antibiotics_Used": 3,
  "Duration_of_Antibiotic_Use": 14,
  "Recent_Surgery": 0,
  "Chronic_Disease": 1,
  "Diabetes": 0,
  "Kidney_Disease": 0,
  "Immunocompromised": 0,
  "Mechanical_Ventilation": 0,
  "Catheter_Use": 1,
  "Infection_Type": "Pneumonia",
  "Pathogen_Type": "MRSA",
  "White_Blood_Cell_Count": 12000,
  "C_Reactive_Protein": 80,
  "Fever": 1,
  "Culture_Test_Positive": 1,
  "Prior_Antibiotic_Failure": 1,
  "Ward_Type": "ICU",
  "Contact_With_MDR_Patient": 1
}
```

## Risk Thresholds
| Classification | Probability Range |
|---|---|
| Low | 0 – 40% |
| Medium | 41 – 70% |
| High | 71 – 100% |

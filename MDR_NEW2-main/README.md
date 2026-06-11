# MDR Disease Risk Prediction & Contact Tracing System

An AI-powered web application for **Multi-Drug Resistant (MDR) disease surveillance** using:
- **XGBoost** — clinical MDR risk prediction
- **Face Recognition** — real-time patient identity matching
- **OpenCV** — webcam/video face detection pipeline
- **MongoDB** — persistent storage for patients, embeddings, contacts, alerts
- **Flask** — backend REST API
- **ReportLab** — professional PDF report generation

---

## System Architecture

```
mdr_app/
├── app.py                    # Flask application factory
├── config.py                 # Configuration settings
├── db_init.py                # DB initialisation & seed script
├── requirements.txt
├── setup_and_run.sh          # Linux/macOS one-command setup
├── run_windows.bat           # Windows one-command setup
├── .env.example              # Environment variable template
│
├── mdr_model/                # Pre-trained XGBoost model
│   ├── xgb_model.joblib
│   ├── label_encoders.joblib
│   └── mdr_predictor.py
│
├── routes/
│   ├── auth.py               # Login, signup, logout
│   ├── admin.py              # Admin-only routes
│   ├── doctor.py             # Doctor routes + webcam API
│   ├── user.py               # Patient portal routes
│   ├── api.py                # REST API for charts/stats
│   └── uploads.py            # Secure file serving
│
├── models/
│   └── user_model.py         # Flask-Login User class
│
├── utils/
│   ├── face_utils.py         # Face embedding & recognition
│   ├── contact_tracing.py    # Proximity, exposure scoring
│   └── pdf_utils.py          # PDF report generation
│
├── templates/
│   ├── shared/               # base.html, landing.html
│   ├── auth/                 # login.html, signup.html
│   ├── admin/                # dashboard, patients, users, alerts, contacts, reports
│   ├── doctor/               # dashboard, register_patient, patient_detail, monitoring
│   └── user/                 # dashboard, my_records, alerts
│
└── uploads/
    ├── patients/             # Patient registration photos
    ├── frames/               # Detected face frames from webcam
    └── reports/              # Generated PDF reports
```

---

## Prerequisites

| Software | Version | Install |
|----------|---------|---------|
| Python   | 3.10–3.11 | https://python.org |
| MongoDB  | 6.0+ | https://www.mongodb.com/try/download/community |
| CMake    | Latest | Required for dlib (face_recognition) |

### Install MongoDB
**Ubuntu/Debian:**
```bash
sudo apt install -y mongodb
sudo systemctl start mongod
sudo systemctl enable mongod
```

**macOS (Homebrew):**
```bash
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community
```

**Windows:** Download installer from https://www.mongodb.com/try/download/community

---

## Quick Start

### Linux / macOS

```bash
# 1. Extract the project zip
unzip mdr_surveillance.zip
cd mdr_app

# 2. Make script executable and run it
chmod +x setup_and_run.sh
./setup_and_run.sh
```

The script will:
- Check Python and MongoDB
- Create a virtual environment
- Install all Python packages
- Initialise MongoDB with indexes
- Prompt you to create an admin account
- Create default doctor and patient accounts
- Start the Flask server on http://localhost:5000

---

### Windows

```
1. Extract mdr_surveillance.zip
2. Double-click run_windows.bat
   (or run it from Command Prompt)
```

---

### Manual Setup (any OS)

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate       # Linux/macOS
# venv\Scripts\activate        # Windows

# 2. Install system dependencies for dlib (Linux only)
sudo apt-get install -y cmake build-essential libopenblas-dev liblapack-dev \
    libx11-dev python3-dev

# 3. Install Python packages
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env if needed (default MongoDB URI is fine for local)

# 5. Create folders
mkdir -p uploads/patients uploads/frames uploads/reports logs

# 6. Initialise database
python db_init.py

# 7. Start application
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Default Login Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `Admin@123` (set during db_init) |
| Doctor | `doctor` | `Doctor@123` |
| Patient | `patient` | `User@123` |

---

## Feature Walkthrough

### 1. Landing Page
- Visit `http://localhost:5000`
- Overview of the system with role descriptions and feature list

### 2. User Authentication
- **Login** — select your role tab (Admin / Doctor / User), enter credentials
- **Signup** — create a new account with role selection
- Sessions are protected with Flask-Login and bcrypt password hashing

### 3. Patient Registration (Doctor)
1. Login as **Doctor**
2. Go to **Register Patient**
3. Fill in all 25 clinical features (age, antibiotics, comorbidities, lab values, etc.)
4. Upload a clear **face photo** for face recognition
5. Submit → XGBoost model predicts MDR risk instantly
6. Patient is saved with face embedding in MongoDB

### 4. Face Recognition
- Face embeddings are generated from uploaded photos using the `face_recognition` library (128-d vectors)
- Embeddings are stored in the `face_embeddings` MongoDB collection
- During live monitoring, detected faces are matched against all stored embeddings
- Cosine distance threshold: 0.5 (configurable in `config.py`)

### 5. Live Monitoring (Doctor)
1. Go to **Live Monitoring** in the sidebar
2. Select your camera from the dropdown
3. Click **Start** — webcam feed begins
4. The system processes frames every ~700ms:
   - Detects faces using `face_recognition` (HOG model)
   - Matches against registered patients
   - Draws color-coded boxes: 🔴 MDR+ | 🟢 MDR-
   - Shows confidence score on each detected face
5. **Upload Video** button lets you analyse a pre-recorded video file

### 6. Contact Tracing
- When two registered persons appear within **150 pixels** of each other (configurable)
- The `ContactTracker` class tracks the contact duration in real-time
- When they separate (or after frame gap), the contact is saved with:
  - Duration, proximity score, exposure risk score
  - If `exposure_risk == High` → automatic CRITICAL alert is created

### 7. Exposure Risk Calculation
```
Exposure Score (0-100) =
    (duration_factor × 40) +
    (mdr_probability × 35) +
    (proximity_score × 25)

Final Risk Score =
    (MDR probability × 60%) + (exposure score × 40%)
```

### 8. PDF Report Generation (Doctor)
1. Open a patient's detail page
2. Click **Generate PDF Report**
3. A professional PDF is generated containing:
   - Patient photo and demographic info
   - XGBoost prediction score and classification
   - Top risk factors with importance chart
   - Contact tracing history
   - Final risk assessment
   - Clinical recommendations
   - Timestamp and unique report ID
4. Download immediately from the toast notification

### 9. Role-Based Access

| Feature | Admin | Doctor | User |
|---------|-------|--------|------|
| View all patients | ✅ | ❌ (own only) | ❌ |
| Register patients | ❌ | ✅ | ❌ |
| Live monitoring | ✅ (view) | ✅ (full) | ❌ |
| Generate reports | ❌ | ✅ | ❌ |
| User management | ✅ | ❌ | ❌ |
| View own records | ❌ | ❌ | ✅ |
| System alerts | ✅ (all) | ✅ (own) | ✅ (own) |

---

## MongoDB Collections

| Collection | Purpose |
|-----------|---------|
| `users` | Authentication accounts |
| `patients` | Patient clinical records + photo path + embedding |
| `face_embeddings` | Fast-lookup face embeddings for matching |
| `predictions` | XGBoost prediction results per patient |
| `contacts` | Completed contact tracing events |
| `alerts` | System alerts (WARNING / CRITICAL) |
| `reports` | PDF report metadata |

---

## Configuration (config.py / .env)

| Key | Default | Description |
|-----|---------|-------------|
| `MONGO_URI` | `mongodb://localhost:27017/mdr_disease_db` | MongoDB connection |
| `SECRET_KEY` | (change this!) | Flask session secret |
| `FACE_RECOGNITION_TOLERANCE` | `0.5` | Lower = stricter matching |
| `CONTACT_DISTANCE_THRESHOLD` | `150` | Pixels for contact proximity |
| `CONTACT_DURATION_THRESHOLD` | `3` | Seconds before contact is logged |
| `HIGH_RISK_EXPOSURE_SCORE` | `60` | Score threshold for HIGH alert |

---

## Troubleshooting

**`dlib` / `face_recognition` installation fails:**
```bash
# Ubuntu — install CMake and build tools first
sudo apt-get install -y cmake build-essential python3-dev
pip install dlib
pip install face_recognition
```

**`face_recognition` not available:**
- The system automatically falls back to OpenCV Haar cascades for face detection
- Face matching accuracy will be reduced but the system remains functional

**MongoDB connection refused:**
```bash
sudo systemctl start mongod        # Linux
brew services start mongodb-community  # macOS
```

**Port 5000 in use:**
Edit `app.py` and change `port=5000` to another port (e.g. `5001`).

**Camera not detected in browser:**
- Use Chrome or Firefox
- Allow camera permissions when prompted
- Make sure no other app is using the camera

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.0, Flask-Login, Flask-Bcrypt |
| Database | MongoDB (via Flask-PyMongo) |
| ML Model | XGBoost (pre-trained, .joblib) |
| Face Recognition | face_recognition 1.3.0 (dlib backend) |
| Computer Vision | OpenCV 4.9 |
| PDF Generation | ReportLab 4.2 |
| Frontend | Bootstrap 5.3, Chart.js 4.4, Font Awesome 6 |

---

*MDR Surveillance System — AI-Powered Disease Risk Management*

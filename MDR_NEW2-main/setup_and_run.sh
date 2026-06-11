#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_and_run.sh — MDR Surveillance System Setup Script
# Works on Ubuntu / Debian / macOS
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     MDR Disease Risk Prediction & Contact Tracing System     ║"
echo "║                  Setup & Launch Script                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Check Python ────────────────────────────────────────────────────────
echo "▶ Checking Python version..."
python_cmd=""
for cmd in python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$($cmd -c "import sys; print(sys.version_info[:2])")
        echo "  Found: $cmd — $ver"
        python_cmd="$cmd"
        break
    fi
done
if [ -z "$python_cmd" ]; then
    echo "❌ Python 3.10+ not found. Please install it first."
    exit 1
fi

# ── 2. Check / start MongoDB ───────────────────────────────────────────────
echo ""
echo "▶ Checking MongoDB..."
if command -v mongod &>/dev/null; then
    if ! pgrep -x mongod &>/dev/null; then
        echo "  MongoDB installed but not running. Attempting to start..."
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            sudo systemctl start mongod 2>/dev/null || sudo service mongod start 2>/dev/null || {
                echo "  Starting mongod in background..."
                mkdir -p /tmp/mdr_mongodata
                mongod --dbpath /tmp/mdr_mongodata --fork --logpath /tmp/mdr_mongo.log
            }
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            brew services start mongodb-community 2>/dev/null || mongod --config /usr/local/etc/mongod.conf --fork 2>/dev/null || true
        fi
    else
        echo "  ✅ MongoDB is running."
    fi
else
    echo "  ⚠️  MongoDB not found. Please install it:"
    echo "     Ubuntu: sudo apt install -y mongodb"
    echo "     macOS:  brew install mongodb-community"
    echo "  Continuing anyway (connect may fail)..."
fi

# ── 3. Virtual environment ─────────────────────────────────────────────────
echo ""
echo "▶ Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    $python_cmd -m venv venv
    echo "  ✅ Virtual environment created."
else
    echo "  ℹ️  Virtual environment already exists."
fi
source venv/bin/activate

# ── 4. System deps for face_recognition (dlib) ────────────────────────────
echo ""
echo "▶ Installing system dependencies for dlib / face_recognition..."
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sudo apt-get update -qq 2>/dev/null || true
    sudo apt-get install -y -qq cmake build-essential libopenblas-dev liblapack-dev \
        libx11-dev libgtk-3-dev libboost-python-dev python3-dev 2>/dev/null || true
elif [[ "$OSTYPE" == "darwin"* ]]; then
    brew install cmake 2>/dev/null || true
fi

# ── 5. Install Python packages ─────────────────────────────────────────────
echo ""
echo "▶ Installing Python packages (this may take a few minutes)..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "  ✅ Packages installed."

# ── 6. Copy .env ───────────────────────────────────────────────────────────
echo ""
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "▶ .env file created from template. Edit it to change settings."
fi

# ── 7. Create required directories ────────────────────────────────────────
mkdir -p uploads/patients uploads/frames uploads/reports logs

# ── 8. Initialise database ─────────────────────────────────────────────────
echo ""
echo "▶ Initialising MongoDB database & default accounts..."
python db_init.py

# ── 9. Launch Flask app ────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  🚀 Starting MDR Surveillance System on http://0.0.0.0:5000 ║"
echo "║  Press Ctrl+C to stop.                                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
python app.py

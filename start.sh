#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================="
echo "   🚀 Starting LeadForge: Autonomous Outreach Engine     "
echo "=========================================================="

# 1. Check Python virtual environment
if [ ! -d "$DIR/.venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install --upgrade pip
    "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
    "$DIR/.venv/bin/playwright" install chromium
fi

# 2. Check Dashboard node_modules
if [ ! -d "$DIR/dashboard/node_modules" ]; then
    echo "Installing Dashboard npm dependencies..."
    cd "$DIR/dashboard"
    npm install --legacy-peer-deps
    cd "$DIR"
fi

# 3. Start Backend
echo "Starting Backend API server on http://localhost:8000..."
cd "$DIR/backend"
"$DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd "$DIR"

# 4. Start Dashboard
echo "Starting Dashboard UI on http://localhost:3000..."
cd "$DIR/dashboard"
npm run dev -- -p 3000 &
FRONTEND_PID=$!
cd "$DIR"

# Cleanup handler on Ctrl+C
cleanup() {
    echo ""
    echo "Shutting down LeadForge services..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

echo ""
echo "=========================================================="
echo " ✅ LeadForge is LIVE and READY!"
echo "   - Web Console: http://localhost:3000"
echo "   - REST API & Swagger Docs: http://localhost:8000/docs"
echo "   - Health Check: http://localhost:8000/health"
echo " Press Ctrl+C to stop all services."
echo "=========================================================="

wait

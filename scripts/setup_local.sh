#!/bin/sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🚀 Setting up local development environment..."
echo ""

# Check for uv
if ! command -v uv >/dev/null 2>&1; then
    echo "❌ Error: uv is required but not found. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check for npm
if ! command -v npm >/dev/null 2>&1; then
    echo "❌ Error: npm is required but not found. Please install Node.js first."
    exit 1
fi

# Check for MongoDB
echo "📦 Checking MongoDB installation..."
if ! command -v mongod >/dev/null 2>&1; then
    echo "   MongoDB not found. Attempting to install..."
    
    # Detect OS
    OS="$(uname -s)"
    case "$OS" in
        Darwin)
            # macOS
            if ! command -v brew >/dev/null 2>&1; then
                echo "❌ Error: Homebrew is required to install MongoDB on macOS."
                echo "   Please install Homebrew first: https://brew.sh"
                exit 1
            fi
            echo "   Installing MongoDB via Homebrew..."
            brew tap mongodb/brew
            brew install mongodb-community
            echo "   ✓ MongoDB installed"
            ;;
        Linux)
            echo "⚠️  MongoDB not found on Linux. Please install MongoDB manually:"
            echo "   https://www.mongodb.com/docs/manual/installation/"
            echo ""
            echo "   Or use Docker Compose instead: docker-compose up"
            ;;
        *)
            echo "⚠️  MongoDB not found. Please install MongoDB manually:"
            echo "   https://www.mongodb.com/docs/manual/installation/"
            ;;
    esac
else
    echo "   ✓ MongoDB already installed"
fi

# Setup Python virtual environment
echo "📦 Setting up Python virtual environment..."
VENV_DIR="$PROJECT_ROOT/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "   Creating venv with uv..."
    uv venv "$VENV_DIR"
    echo "   ✓ Virtual environment created"
else
    echo "   ✓ Virtual environment already exists"
fi

# Activate venv
echo "   Activating venv..."
. "$VENV_DIR/bin/activate"

# Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
python <<EOF > /tmp/requirements.txt
from pathlib import Path
from tomllib import load
data = load(Path('pyproject.toml').open('rb'))
deps = data['project']['dependencies']
dev_deps = data['project']['optional-dependencies']['dev']
print('\n'.join(deps + dev_deps))
EOF

uv pip install -r /tmp/requirements.txt
rm /tmp/requirements.txt
echo "   ✓ Python dependencies installed"

# Setup frontend
echo ""
echo "📦 Setting up frontend dependencies..."
cd "$PROJECT_ROOT/frontend"
if [ ! -f "node_modules/.bin/vite" ]; then
    echo "   Running npm install..."
    npm install
    echo "   ✓ Frontend dependencies installed"
else
    echo "   ✓ Frontend dependencies already installed"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Start MongoDB:     ./scripts/start_mongodb.sh"
echo "  2. Start backend:     ./scripts/start_backend.sh"
echo "  3. Start worker:      ./scripts/start_worker.sh"
echo "  4. Start frontend:    ./scripts/start_frontend.sh"
echo ""
echo "Or use Docker Compose:"
echo "  docker-compose up"


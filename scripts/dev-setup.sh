#!/usr/bin/env bash
# dev-setup.sh — AI Helpdesk Assistant developer setup
# Run this once after cloning to pull Ollama models and install all deps.
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║   AI Helpdesk Assistant — Developer Setup     ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# ── Prerequisites check ──────────────────────────────────────────────────────
info "Checking prerequisites..."

command -v node   >/dev/null 2>&1 || error "Node.js ≥20 not found. Install from https://nodejs.org"
command -v npm    >/dev/null 2>&1 || error "npm not found"
command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1 || error "Python 3.11+ not found"
command -v uv     >/dev/null 2>&1 || error "uv not found. Install: pip install uv or curl -Ls https://astral.sh/uv/install.sh | sh"
command -v ollama >/dev/null 2>&1 || error "Ollama not found. Install from https://ollama.com"
command -v git    >/dev/null 2>&1 || error "git not found"

NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 20 ]; then
  error "Node.js 20+ required (found $(node --version))"
fi

success "All prerequisites found"

# ── Ollama models ─────────────────────────────────────────────────────────────
info "Pulling Ollama models (this may take a few minutes)..."

if ! ollama list 2>/dev/null | grep -q "llama3.2:3b"; then
  info "Pulling llama3.2:3b..."
  ollama pull llama3.2:3b
  success "llama3.2:3b pulled"
else
  success "llama3.2:3b already present"
fi

if ! ollama list 2>/dev/null | grep -q "nomic-embed-text"; then
  info "Pulling nomic-embed-text..."
  ollama pull nomic-embed-text
  success "nomic-embed-text pulled"
else
  success "nomic-embed-text already present"
fi

# ── Extension dependencies ────────────────────────────────────────────────────
info "Installing extension dependencies..."
cd extension
npm install
cd ..
success "Extension dependencies installed"

# ── Backend dependencies ──────────────────────────────────────────────────────
info "Installing backend Python dependencies..."
cd backend
uv sync --dev
cd ..
success "Backend dependencies installed"

# ── Worktrees directory ───────────────────────────────────────────────────────
WORKTREE_DIR="../assistant-worktrees"
if [ ! -d "$WORKTREE_DIR" ]; then
  mkdir -p "$WORKTREE_DIR"
  success "Created worktrees directory: $WORKTREE_DIR"
else
  success "Worktrees directory already exists"
fi

# ── Final instructions ────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║              Setup Complete!                  ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Start Ollama:         ollama serve"
echo "  2. Start backend:        cd backend && uv run uvicorn app.main:app --port 8765 --reload"
echo "  3. Build extension:      cd extension && npm run build"
echo "  4. Load in Edge:         edge://extensions → Load unpacked → select extension/dist/"
echo "  5. Open a WHD ticket and press Alt+Shift+H to open the sidebar"
echo ""
echo "Ingest your data:"
echo "  cd backend"
echo "  uv run python -m ingestion.cli ingest-tickets <export.json>"
echo "  uv run python -m ingestion.cli ingest-kb-html <./kb_articles/>"
echo "  uv run python -m ingestion.cli status"
echo ""

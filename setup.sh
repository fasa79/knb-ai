#!/usr/bin/env bash
# ──────────────────────────────────────────────
# Khazanah Annual Review AI — One-Command Setup
# ──────────────────────────────────────────────
# Usage: ./setup.sh
#   or:  bash setup.sh
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║   Khazanah Annual Review AI — Setup       ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ── Check Docker ──────────────────────────────
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed.${NC}"
    echo "Install Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &> /dev/null 2>&1; then
    echo -e "${RED}Error: Docker daemon is not running.${NC}"
    echo "Please start Docker Desktop and try again."
    exit 1
fi

echo -e "${GREEN}✓ Docker is running${NC}"

# ── Collect API Key ──────────────────────────
if [ -f .env ]; then
    EXISTING_KEY=$(grep -oP 'GEMINI_API_KEY=\K.+' .env 2>/dev/null || true)
    if [ -n "$EXISTING_KEY" ] && [ "$EXISTING_KEY" != "your-gemini-api-key-here" ]; then
        echo -e "${GREEN}✓ Found existing .env with API key${NC}"
        read -p "Use existing key? (Y/n): " USE_EXISTING
        if [ "${USE_EXISTING,,}" != "n" ]; then
            echo "  Using existing .env"
            SKIP_ENV=true
        fi
    fi
fi

if [ "$SKIP_ENV" != "true" ]; then
    echo ""
    echo -e "${YELLOW}You need a Google Gemini API key (free).${NC}"
    echo "Get one at: https://aistudio.google.com/apikey"
    echo ""
    read -p "Enter your Gemini API key: " API_KEY

    if [ -z "$API_KEY" ]; then
        echo -e "${RED}Error: API key cannot be empty.${NC}"
        exit 1
    fi

    # Generate .env from template
    cp .env.example .env
    sed -i "s|GEMINI_API_KEY=your-gemini-api-key-here|GEMINI_API_KEY=${API_KEY}|" .env
    echo -e "${GREEN}✓ Created .env with your API key${NC}"
fi

# ── Build & Start ─────────────────────────────
echo ""
echo "Building and starting services (this may take a few minutes on first run)..."
echo ""

docker compose up --build -d

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   All services are running!               ║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║   Frontend:  http://localhost:3000        ║${NC}"
echo -e "${GREEN}║   API Docs:  http://localhost:8000/docs   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:3000"
echo "  2. Upload PDFs on the Documents page"
echo "  3. Click 'Run Ingestion' to process them"
echo "  4. Go to Chat and start asking questions!"
echo ""
echo "To stop:  docker compose down"
echo "To logs:  docker compose logs -f"

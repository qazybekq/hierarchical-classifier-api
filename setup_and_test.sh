#!/bin/bash
# Setup and Test Script for Hierarchical Classification API
# This script will build and test your Docker container

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Hierarchical Classification API - Setup & Test              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Docker is installed
echo -e "${YELLOW}[1/7] Checking Docker installation...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed!${NC}"
    echo "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
fi
echo -e "${GREEN}✓ Docker is installed${NC}"
echo ""

# Check if Docker is running
echo -e "${YELLOW}[2/7] Checking if Docker is running...${NC}"
if ! docker info &> /dev/null; then
    echo -e "${RED}✗ Docker is not running!${NC}"
    echo "Please start Docker Desktop and try again."
    exit 1
fi
echo -e "${GREEN}✓ Docker is running${NC}"
echo ""

# Build Docker image
echo -e "${YELLOW}[3/7] Building Docker image...${NC}"
echo "This may take a few minutes on first build..."
if docker compose build; then
    echo -e "${GREEN}✓ Docker image built successfully${NC}"
else
    echo -e "${RED}✗ Docker build failed!${NC}"
    exit 1
fi
echo ""

# Start the container
echo -e "${YELLOW}[4/7] Starting Docker container...${NC}"
if docker compose up -d; then
    echo -e "${GREEN}✓ Container started${NC}"
else
    echo -e "${RED}✗ Failed to start container${NC}"
    exit 1
fi
echo ""

# Wait for service to be ready
echo -e "${YELLOW}[5/7] Waiting for service to be ready...${NC}"
echo "This may take 30-60 seconds as models load into memory..."
MAX_WAIT=120
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Service is ready!${NC}"
        break
    fi
    echo -n "."
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "${RED}✗ Service did not start in time${NC}"
    echo "Checking logs..."
    docker compose logs --tail=50
    exit 1
fi
echo ""

# Test health endpoint
echo -e "${YELLOW}[6/7] Testing health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:8001/health)
if echo "$HEALTH_RESPONSE" | grep -q "ok"; then
    echo -e "${GREEN}✓ Health check passed${NC}"
    echo "Response: $HEALTH_RESPONSE"
else
    echo -e "${RED}✗ Health check failed${NC}"
    echo "Response: $HEALTH_RESPONSE"
    exit 1
fi
echo ""

# Test prediction endpoint
echo -e "${YELLOW}[7/7] Testing prediction endpoint...${NC}"
TEST_TEXT="Прошу разобраться с начислением штрафа по налогам"
echo "Test text: $TEST_TEXT"
echo ""

PRED_RESPONSE=$(curl -s -X POST http://localhost:8001/predict \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$TEST_TEXT\", \"topk_cat\": 2, \"topk_sub\": 3}")

if echo "$PRED_RESPONSE" | grep -q "predictions"; then
    echo -e "${GREEN}✓ Prediction test passed${NC}"
    echo ""
    echo "Top prediction:"
    echo "$PRED_RESPONSE" | python3 -m json.tool | head -20
else
    echo -e "${RED}✗ Prediction test failed${NC}"
    echo "Response: $PRED_RESPONSE"
    exit 1
fi
echo ""

# Success summary
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    ✓ ALL TESTS PASSED! ✓                            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Your API is now running at:${NC} http://localhost:8001"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  • View logs:       docker compose logs -f"
echo "  • Stop service:    docker compose down"
echo "  • Restart:         docker compose restart"
echo "  • Run tests:       python test_api.py"
echo ""
echo -e "${BLUE}Next step:${NC} Push to GitHub using ./push_to_github.sh"
echo ""


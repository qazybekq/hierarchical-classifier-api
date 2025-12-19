#!/bin/bash
# GitHub Setup Script for Hierarchical Classification API
# This script will help you push your code to GitHub

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              GitHub Repository Setup & Push                          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}✗ Git is not installed!${NC}"
    exit 1
fi

# Check current git status
echo -e "${YELLOW}Checking Git status...${NC}"
git status
echo ""

# Check if remote already exists
if git remote get-url origin &> /dev/null; then
    echo -e "${GREEN}✓ Git remote 'origin' already configured${NC}"
    REMOTE_URL=$(git remote get-url origin)
    echo "Current remote: $REMOTE_URL"
    echo ""
    
    read -p "Do you want to push to this remote? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Exiting..."
        exit 0
    fi
else
    echo -e "${YELLOW}No remote repository configured yet.${NC}"
    echo ""
    echo "Please follow these steps:"
    echo ""
    echo -e "${BLUE}STEP 1:${NC} Create a repository on GitHub"
    echo "   1. Go to https://github.com/new"
    echo "   2. Repository name: hierarchical-classifier-api"
    echo "   3. Description: Hierarchical text classification API using sentence transformers"
    echo "   4. Choose: Public or Private"
    echo "   5. DO NOT initialize with README, .gitignore, or license"
    echo "   6. Click 'Create repository'"
    echo ""
    echo -e "${BLUE}STEP 2:${NC} Enter your repository URL"
    echo ""
    
    read -p "Enter your GitHub username: " GITHUB_USERNAME
    read -p "Enter repository name [hierarchical-classifier-api]: " REPO_NAME
    REPO_NAME=${REPO_NAME:-hierarchical-classifier-api}
    
    REMOTE_URL="https://github.com/${GITHUB_USERNAME}/${REPO_NAME}.git"
    
    echo ""
    echo "Will add remote: $REMOTE_URL"
    read -p "Is this correct? (y/n): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Exiting..."
        exit 0
    fi
    
    echo ""
    echo -e "${YELLOW}Adding remote repository...${NC}"
    git remote add origin "$REMOTE_URL"
    echo -e "${GREEN}✓ Remote added${NC}"
fi

echo ""
echo -e "${YELLOW}Pushing to GitHub...${NC}"
echo "This may ask for your GitHub credentials..."
echo ""

# Ensure we're on main branch
git branch -M main

# Push to GitHub
if git push -u origin main; then
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              ✓ SUCCESSFULLY PUSHED TO GITHUB! ✓                     ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BLUE}Your repository is now live at:${NC}"
    echo "  https://github.com/${GITHUB_USERNAME}/${REPO_NAME}"
    echo ""
    echo -e "${BLUE}Others can now clone and use your API:${NC}"
    echo "  git clone $REMOTE_URL"
    echo "  cd $REPO_NAME"
    echo "  docker compose up -d"
    echo ""
    echo -e "${GREEN}🎉 Your microservice is now publicly available! 🎉${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}✗ Push failed!${NC}"
    echo ""
    echo "Common issues:"
    echo "  1. Authentication failed - you may need a Personal Access Token"
    echo "     Go to: https://github.com/settings/tokens"
    echo "     Generate a new token with 'repo' scope"
    echo "     Use the token as your password"
    echo ""
    echo "  2. Remote repository already has content"
    echo "     Try: git pull origin main --allow-unrelated-histories"
    echo "     Then: git push -u origin main"
    echo ""
    echo "  3. Using SSH instead of HTTPS"
    echo "     Use: git@github.com:${GITHUB_USERNAME}/${REPO_NAME}.git"
    echo ""
    exit 1
fi




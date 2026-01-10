#!/bin/bash
set -e

# Docker Setup Validation Script for AnO-Reborn
# This script checks if your environment is ready for Docker

echo "======================================"
echo "AnO-Reborn Docker Setup Validator"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check functions
check_passed=0
check_failed=0

check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✓${NC} $2 is installed"
        ((check_passed++))
        return 0
    else
        echo -e "${RED}✗${NC} $2 is not installed"
        echo "  Install from: $3"
        ((check_failed++))
        return 1
    fi
}

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $2 exists"
        ((check_passed++))
        return 0
    else
        echo -e "${YELLOW}⚠${NC} $2 is missing"
        echo "  $3"
        ((check_failed++))
        return 1
    fi
}

# Check Docker
echo "Checking Docker installation..."
check_command "docker" "Docker" "https://docs.docker.com/get-docker/"

if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    echo "  Version: $docker_version"
fi

echo ""

# Check Docker Compose
echo "Checking Docker Compose..."
if docker compose version &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker Compose (v2) is available"
    ((check_passed++))
    compose_version=$(docker compose version)
    echo "  Version: $compose_version"
elif command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker Compose (v1) is available"
    ((check_passed++))
    compose_version=$(docker-compose --version)
    echo "  Version: $compose_version"
    echo -e "${YELLOW}  Note: Consider upgrading to Docker Compose v2${NC}"
else
    echo -e "${RED}✗${NC} Docker Compose is not available"
    echo "  Docker Compose should be included with Docker Desktop"
    ((check_failed++))
fi

echo ""

# Check required files
echo "Checking required files..."
check_file "Dockerfile" "Dockerfile" "This should exist in the repository"
check_file "docker-compose.yml" "docker-compose.yml" "This should exist in the repository"
check_file ".dockerignore" ".dockerignore" "This should exist in the repository"

echo ""

# Check .env file
echo "Checking environment configuration..."
if check_file ".env" ".env file" "Copy from .env.docker.example: cp .env.docker.example .env"; then
    # Check if .env has been customized
    if grep -q "change_this_password_for_production" .env 2>/dev/null; then
        echo -e "${YELLOW}  ⚠ Warning: .env still contains default passwords${NC}"
        echo "  Please edit .env and change the passwords and SECRET_KEY"
    fi
fi

echo ""

# Check Docker daemon
echo "Checking Docker daemon..."
if docker info &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker daemon is running"
    ((check_passed++))
else
    echo -e "${RED}✗${NC} Docker daemon is not running"
    echo "  Start Docker Desktop or the Docker service"
    ((check_failed++))
fi

echo ""

# Summary
echo "======================================"
echo "Summary"
echo "======================================"
echo -e "Checks passed: ${GREEN}${check_passed}${NC}"
echo -e "Checks failed: ${RED}${check_failed}${NC}"
echo ""

if [ $check_failed -eq 0 ]; then
    echo -e "${GREEN}✓ Your environment is ready for Docker!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review and customize .env file"
    echo "  2. Run: docker compose up --build"
    echo "  3. Access http://localhost:5000"
    exit 0
else
    echo -e "${RED}✗ Please fix the issues above before proceeding${NC}"
    exit 1
fi

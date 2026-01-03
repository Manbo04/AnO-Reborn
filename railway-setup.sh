#!/bin/bash
# Railway Database Connection Fix Script
# Run this to configure Railway environment variables correctly

echo "=================================================="
echo "Railway Database Connection Fix"
echo "=================================================="
echo ""

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    echo ""
    echo "Run this command first:"
    echo "  npm i -g @railway/cli"
    echo ""
    echo "Or use brew:"
    echo "  brew install railway"
    echo ""
    exit 1
fi

echo "✅ Railway CLI found"
echo ""

# Link to project if not already linked
echo "Checking Railway project link..."
railway status &> /dev/null
if [ $? -ne 0 ]; then
    echo "❌ Not linked to Railway project"
    echo "Run: railway link"
    exit 1
fi

echo "✅ Railway project linked"
echo ""

# Set environment variables using Railway variable references
echo "Setting environment variables..."
echo ""

# Set DATABASE_URL to reference the Postgres service
echo "Setting DATABASE_URL to reference Postgres service..."
railway variables --set "DATABASE_URL=\${{Postgres.DATABASE_URL}}" 2>&1 | grep -v "warning"

echo "Setting DATABASE_PUBLIC_URL to reference Postgres service..."
railway variables --set "DATABASE_PUBLIC_URL=\${{Postgres.DATABASE_PUBLIC_URL}}" 2>&1 | grep -v "warning"

echo ""
echo "✅ Environment variables configured"
echo ""
echo "=================================================="
echo "Redeploying services..."
echo "=================================================="
echo ""

# Trigger redeploy
railway up --detach

echo ""
echo "✅ Deployment triggered"
echo ""
echo "=================================================="
echo "Monitor deployment:"
echo "  railway logs"
echo ""
echo "Check status:"
echo "  railway status"
echo "=================================================="

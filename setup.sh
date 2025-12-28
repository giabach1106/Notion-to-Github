#!/bin/bash
# Quick Setup Script for Notion Backup System

set -e

echo "=========================================="
echo "Notion Backup System - Quick Setup"
echo "=========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first:"
    echo "   https://docs.docker.com/engine/install/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install it first:"
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker is installed"
echo "✅ Docker Compose is installed"
echo ""

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p notion-backup-repo
mkdir -p logs
echo "✅ Directories created"
echo ""

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  No .env file found"
    
    if [ -f .env.example ]; then
        echo "📝 Copying .env.example to .env..."
        cp .env.example .env
        echo "✅ Created .env file"
        echo ""
        echo "⚠️  IMPORTANT: You must edit .env with your credentials!"
        echo "   Run: nano .env"
        echo ""
        read -p "Would you like to edit .env now? (y/n) " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        fi
    else
        echo "❌ .env.example not found. Please create .env manually."
        exit 1
    fi
else
    echo "✅ .env file exists"
fi
echo ""

# Check SSH key
echo "🔑 Checking SSH key for GitHub..."
if [ ! -f ~/.ssh/id_rsa ] && [ ! -f ~/.ssh/id_ed25519 ]; then
    echo "⚠️  No SSH key found"
    echo ""
    read -p "Would you like to generate an SSH key now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your email for SSH key: " email
        ssh-keygen -t ed25519 -C "$email"
        echo ""
        echo "✅ SSH key generated"
        echo "📋 Your public key:"
        cat ~/.ssh/id_ed25519.pub
        echo ""
        echo "⚠️  Add this key to GitHub: https://github.com/settings/keys"
        echo ""
        read -p "Press Enter after adding the key to GitHub..."
    fi
else
    echo "✅ SSH key found"
fi
echo ""

# Test GitHub connection
echo "🔗 Testing GitHub connection..."
if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo "✅ GitHub SSH authentication works"
else
    echo "⚠️  Could not verify GitHub connection"
    echo "   Make sure your SSH key is added to GitHub"
fi
echo ""

# Validate .env configuration
echo "🔍 Validating configuration..."
source .env

errors=0

if [ -z "$NOTION_TOKEN_V2" ] || [ "$NOTION_TOKEN_V2" = "your_token_v2_here" ]; then
    echo "❌ NOTION_TOKEN_V2 is not set"
    errors=$((errors + 1))
fi

if [ -z "$NOTION_SPACE_ID" ] || [ "$NOTION_SPACE_ID" = "your_space_id_here" ]; then
    echo "❌ NOTION_SPACE_ID is not set"
    errors=$((errors + 1))
fi

if [ -z "$GITHUB_REPO_URL" ] || [[ "$GITHUB_REPO_URL" == *"yourusername"* ]]; then
    echo "❌ GITHUB_REPO_URL is not set correctly"
    errors=$((errors + 1))
fi

if [ $errors -gt 0 ]; then
    echo ""
    echo "❌ Configuration incomplete. Please edit .env:"
    echo "   nano .env"
    exit 1
fi

echo "✅ Configuration looks good"
echo ""

# Build Docker image
echo "🔨 Building Docker image..."
if docker-compose build; then
    echo "✅ Docker image built successfully"
else
    echo "❌ Failed to build Docker image"
    exit 1
fi
echo ""

# Start service
echo "🚀 Starting backup service..."
if docker-compose up -d; then
    echo "✅ Service started successfully"
else
    echo "❌ Failed to start service"
    exit 1
fi
echo ""

# Show logs
echo "📊 Showing logs (Ctrl+C to exit)..."
echo "=========================================="
echo ""
sleep 2
docker-compose logs -f

# Note: The script will continue showing logs until Ctrl+C
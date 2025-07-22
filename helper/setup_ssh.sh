#!/bin/bash

# === CONFIG ===
EMAIL="your_email@example.com"
KEY_PATH="$HOME/.ssh/id_ed25519"

# === STEP 1: Generate SSH key ===
echo "🔐 Generating new SSH key..."
ssh-keygen -t ed25519 -C "$EMAIL" -f "$KEY_PATH" -N ""

# === STEP 2: Start SSH agent ===
echo "🚀 Starting ssh-agent..."
eval "$(ssh-agent -s)"

# === STEP 3: Add key to agent ===
echo "➕ Adding SSH key to agent..."
ssh-add "$KEY_PATH"

# === STEP 4: Show the public key ===
echo "📋 Copy the following SSH public key and add it to GitHub:"
echo "👉 https://github.com/settings/ssh/new"
echo "=========================================================="
cat "$KEY_PATH.pub"
echo "=========================================================="

# === STEP 5: Optionally test connection (user interaction required) ===
echo "✅ Done. You can now test with: ssh -T git@github.com"


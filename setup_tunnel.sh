#!/bin/bash
# Sets up Cloudflare Tunnel: ampav.timaeus.ai → localhost:5000
set -e

echo "=== Cloudflare Tunnel Setup for timaeus.ai/ampav ==="
echo ""

# Install cloudflared
if ! command -v cloudflared &>/dev/null; then
  echo "Installing cloudflared..."
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
  sudo apt-get update -q && sudo apt-get install -y cloudflared
  echo "cloudflared installed."
fi

echo "Step 1: Log in to Cloudflare (a browser tab will open)"
cloudflared tunnel login

echo ""
echo "Step 2: Creating tunnel named 'ampav'..."
cloudflared tunnel create ampav

TUNNEL_ID=$(cloudflared tunnel list | grep '\bampav\b' | awk '{print $1}')
echo "  Tunnel ID: $TUNNEL_ID"

echo ""
echo "Step 3: Writing tunnel config..."
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml <<EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: ampav.timaeus.ai
    service: http://localhost:5000
  - service: http_status:404
EOF

echo ""
echo "Step 4: Adding DNS record (ampav.timaeus.ai → tunnel)..."
cloudflared tunnel route dns ampav ampav.timaeus.ai

echo ""
echo "=== Done! ==="
echo ""
echo "Start the tunnel with:"
echo "  cloudflared tunnel run ampav"
echo ""
echo "Then deploy cloudflare-worker.js in the Cloudflare dashboard."
echo "  Your POS:   https://timaeus.ai/ampav"
echo "  Your admin: https://timaeus.ai/ampav/log"

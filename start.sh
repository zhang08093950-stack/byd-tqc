#!/bin/bash

LOGDIR="/Users/xinpengzhang/.claude/tqc"
cd "$LOGDIR"

echo "=== TQC Server ==="

# Start Flask server in background
python3 server.py > "$LOGDIR/server.log" 2>&1 &
echo "Server PID: $!"

# Start cloudflared in background
cloudflared tunnel --url http://localhost:8789 > "$LOGDIR/tunnel.log" 2>&1 &
echo "Tunnel PID: $!"

# Wait for and display the public URL
for i in $(seq 1 20); do
  sleep 1
  URL=$(grep -oE 'https://[a-z0-9]+(-[a-z0-9]+)*\.trycloudflare\.com' "$LOGDIR/tunnel.log" 2>/dev/null | head -1)
  if [ -n "$URL" ]; then
    echo ""
    echo "=============================================="
    echo "  $URL"
    echo "=============================================="
    echo ""
    break
  fi
done

wait

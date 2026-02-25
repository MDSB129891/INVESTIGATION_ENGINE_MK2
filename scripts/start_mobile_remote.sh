#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8765}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "❌ tailscale CLI not found. Install/start Tailscale first."
  exit 1
fi

TS_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
if [[ -z "${TS_IP}" ]]; then
  echo "❌ Tailscale is not connected on this Mac."
  echo "Run: tailscale up"
  exit 1
fi

echo "✅ Tailscale connected: ${TS_IP}"
echo "📱 Phone URL (remote): http://${TS_IP}:${PORT}"
echo "🌐 Local URL: http://127.0.0.1:${PORT}"
echo ""

exec ./scripts/run_mobile_console.sh

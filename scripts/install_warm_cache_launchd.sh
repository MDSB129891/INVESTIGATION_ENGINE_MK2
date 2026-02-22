#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.ironlegion.warmcache.plist"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python3}"
TICKERS="${WARM_CACHE_UNIVERSE:-AAPL,MSFT,GOOGL,NVDA,AMZN,META,TSLA,WMT,GM}"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ironlegion.warmcache</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$ROOT/scripts/warm_cache_nightly.py</string>
    <string>--tickers</string>
    <string>$TICKERS</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>10</integer>
  </dict>
  <key>StandardOutPath</key><string>$ROOT/outputs/warm_cache_launchd.log</string>
  <key>StandardErrorPath</key><string>$ROOT/outputs/warm_cache_launchd.err.log</string>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
echo "Installed launchd job: $PLIST"
echo "Run now: launchctl start com.ironlegion.warmcache"


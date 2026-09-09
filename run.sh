#!/usr/bin/env bash
# Start the Telangana news radar and open the dashboard.
set -euo pipefail
cd "$(dirname "$0")"

# Optional extras — uncomment and fill in if you want them.
# export GROQ_API_KEY="your-groq-free-key"
# export RADAR_TELEGRAM_TOKEN="123456:ABC..."
# export RADAR_TELEGRAM_CHAT="-1001234567890"

exec python3 -m radar "$@"

#!/usr/bin/env bash
set -euo pipefail

pkill -f "pincabos-web-display-screen-" 2>/dev/null || true
pkill -f "/tmp/pincabos-web-display-screen-" 2>/dev/null || true

echo "OK: fenêtres PinCabOs Web fermées"

#!/usr/bin/env bash
set -euo pipefail

SCREEN="${1:-0}"
URL="${2:-http://127.0.0.1/}"

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/pinball/.Xauthority}"

LOG="/tmp/pincabos-launch-webapp-screen-${SCREEN}.log"

echo "=== PinCabOs launch-webapp-screen ===" > "$LOG"
echo "Date: $(date)" >> "$LOG"
echo "Screen: $SCREEN" >> "$LOG"
echo "URL: $URL" >> "$LOG"
echo "DISPLAY: $DISPLAY" >> "$LOG"
echo "XAUTHORITY: $XAUTHORITY" >> "$LOG"

BROWSER=""

# Priorité PinCabOS : Chromium local VPinFE, car Snap/Chromium système a été retiré.
if [ -x "/opt/pincabos/apps/frontend/vpinfe/chromium/linux/chrome/chrome" ]; then
  BROWSER="/opt/pincabos/apps/frontend/vpinfe/chromium/linux/chrome/chrome"
else
  for b in chromium-browser chromium google-chrome google-chrome-stable; do
    if command -v "$b" >/dev/null 2>&1; then
      BROWSER="$b"
      break
    fi
  done
fi

if [ -z "$BROWSER" ]; then
  echo "ERREUR: chromium/chrome introuvable" >> "$LOG"
  exit 1
fi

echo "Browser: $BROWSER" >> "$LOG"

GEOM=""

if command -v xrandr >/dev/null 2>&1; then
  echo "=== XRANDR ===" >> "$LOG"
  xrandr --query >> "$LOG" 2>&1 || true

  if [ "$SCREEN" = "1" ]; then
    GEOM="$(xrandr --query 2>/dev/null | awk '/ connected/{print $3}' | grep -E '^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+' | sed -n '2p' || true)"
  else
    GEOM="$(xrandr --query 2>/dev/null | awk '/ connected/{print $3}' | grep -E '^[0-9]+x[0-9]+\+[0-9]+\+[0-9]+' | sed -n '1p' || true)"
  fi
fi

if [ -z "$GEOM" ]; then
  GEOM="1280x800+0+0"
fi

W="$(echo "$GEOM" | sed -E 's/^([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)$/\1/')"
H="$(echo "$GEOM" | sed -E 's/^([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)$/\2/')"
X="$(echo "$GEOM" | sed -E 's/^([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)$/\3/')"
Y="$(echo "$GEOM" | sed -E 's/^([0-9]+)x([0-9]+)\+([0-9]+)\+([0-9]+)$/\4/')"

echo "Geometry: $GEOM" >> "$LOG"
echo "Window: ${W}x${H}+${X}+${Y}" >> "$LOG"

pkill -f "pincabos-web-display-screen-${SCREEN}" 2>/dev/null || true

sudo -u pinball env DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" "$BROWSER" \
  --user-data-dir="/tmp/pincabos-web-display-screen-${SCREEN}" \
  --class="pincabos-web-display-screen-${SCREEN}" \
  --window-position="$X,$Y" \
  --window-size="$W,$H" \
  --kiosk \
  --app="$URL" \
  --no-first-run \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --disable-background-networking \
  --disable-component-update \
  --disable-default-apps \
  --autoplay-policy=no-user-gesture-required \
  --test-type \
  --no-sandbox \
  --disable-dev-shm-usage \
  >> "$LOG" 2>&1 &

echo "OK lancé" >> "$LOG"
exit 0

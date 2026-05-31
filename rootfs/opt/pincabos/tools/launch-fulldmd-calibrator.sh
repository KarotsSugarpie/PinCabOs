#!/usr/bin/env bash
set -u
set -o pipefail

LOG="/opt/pincabos/logs/fulldmd-live.log"
URL="http://127.0.0.1/fulldmd-screen"
PROFILE="/tmp/pincabos-fulldmd-calibrator-profile"

mkdir -p "$(dirname "$LOG")"

{
echo
echo "=================================================="
echo "$(date '+%F %T') - Launch PinCabOS FullDMD calibrator"
echo "Priority: screen id 2, fallback 1, fallback 0"
echo "URL: $URL"
echo "=================================================="
} >> "$LOG"

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/pinball/.Xauthority}"

# Trouver chromium/chrome.
BROWSER=""
for b in chromium chromium-browser google-chrome google-chrome-stable; do
  if command -v "$b" >/dev/null 2>&1; then
    BROWSER="$(command -v "$b")"
    break
  fi
done

if [ -z "$BROWSER" ]; then
  echo "ERREUR: aucun navigateur Chromium/Chrome trouvé." >> "$LOG"
  exit 1
fi

# Lire les moniteurs via xrandr --listmonitors.
XRANDR_OUT="$(DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" xrandr --listmonitors 2>/dev/null || true)"

{
echo "--- xrandr --listmonitors ---"
echo "$XRANDR_OUT"
} >> "$LOG"

pick_monitor_line() {
  local wanted="$1"
  echo "$XRANDR_OUT" | awk -v id="${wanted}:" '$1 == id {print; exit}'
}

MON_LINE=""
MON_ID=""

for id in 2 1 0; do
  line="$(pick_monitor_line "$id")"
  if [ -n "$line" ]; then
    MON_LINE="$line"
    MON_ID="$id"
    break
  fi
done

if [ -z "$MON_LINE" ]; then
  echo "WARNING: impossible de lire les moniteurs xrandr. Fallback 0,0 1280x720." >> "$LOG"
  X=0
  Y=0
  W=1280
  H=720
else
  # Exemple ligne:
  # 2: +HDMI-1 1920/520x1080/290+3840+0  HDMI-1
  GEOM="$(echo "$MON_LINE" | grep -oE '[0-9]+/[0-9]+x[0-9]+/[0-9]+\+[0-9]+\+[0-9]+' | head -n 1)"

  if [ -z "$GEOM" ]; then
    echo "WARNING: géométrie introuvable dans: $MON_LINE" >> "$LOG"
    X=0
    Y=0
    W=1280
    H=720
  else
    W="$(echo "$GEOM" | sed -E 's#^([0-9]+)/[0-9]+x([0-9]+)/[0-9]+\+([0-9]+)\+([0-9]+)$#\1#')"
    H="$(echo "$GEOM" | sed -E 's#^([0-9]+)/[0-9]+x([0-9]+)/[0-9]+\+([0-9]+)\+([0-9]+)$#\2#')"
    X="$(echo "$GEOM" | sed -E 's#^([0-9]+)/[0-9]+x([0-9]+)/[0-9]+\+([0-9]+)\+([0-9]+)$#\3#')"
    Y="$(echo "$GEOM" | sed -E 's#^([0-9]+)/[0-9]+x([0-9]+)/[0-9]+\+([0-9]+)\+([0-9]+)$#\4#')"
  fi
fi

{
echo "Selected monitor id: ${MON_ID:-fallback}"
echo "Selected monitor line: ${MON_LINE:-none}"
echo "Geometry: ${W}x${H}+${X}+${Y}"
echo "Browser: $BROWSER"
} >> "$LOG"

# Fermer ancien calibrateur seulement.
pkill -f 'pincabos-fulldmd-calibrator|/fulldmd-screen' 2>/dev/null || true
sleep 0.5

rm -rf "$PROFILE" 2>/dev/null || true
mkdir -p "$PROFILE"
chown -R pinball:pinball "$PROFILE" 2>/dev/null || true

CMD=(
  "$BROWSER"
  --no-sandbox
  --test-type
  --noerrdialogs
  --disable-infobars
  --disable-session-crashed-bubble
  --disable-restore-session-state
  --disable-background-networking
  --disable-component-update
  --disable-default-apps
  --disable-dev-shm-usage
  --password-store=basic
  --use-mock-keychain
  --user-data-dir="$PROFILE"
  --class=pincabos-fulldmd-calibrator
  --window-name=pincabos-fulldmd-calibrator
  --window-position="${X},${Y}"
  --window-size="${W},${H}"
  --app="$URL"
)

{
echo "--- command ---"
printf '%q ' "${CMD[@]}"
echo
} >> "$LOG"

# Lancer comme pinball si on est root.
if [ "$(id -u)" = "0" ]; then
  sudo -u pinball DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" nohup "${CMD[@]}" >> "$LOG" 2>&1 &
else
  nohup "${CMD[@]}" >> "$LOG" 2>&1 &
fi

sleep 1

# Essayer fullscreen via wmctrl/xdotool après ouverture.
if command -v wmctrl >/dev/null 2>&1; then
  DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" wmctrl -r "pincabos-fulldmd-calibrator" -b add,fullscreen >> "$LOG" 2>&1 || true
fi

if command -v xdotool >/dev/null 2>&1; then
  WIN="$(DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" xdotool search --name "pincabos-fulldmd-calibrator" 2>/dev/null | head -n 1 || true)"
  if [ -n "$WIN" ]; then
    DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" xdotool windowmove "$WIN" "$X" "$Y" windowsize "$WIN" "$W" "$H" >> "$LOG" 2>&1 || true
    DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" xdotool windowactivate "$WIN" key F11 >> "$LOG" 2>&1 || true
  fi
fi

echo "$(date '+%F %T') - FullDMD calibrator launch done" >> "$LOG"
exit 0

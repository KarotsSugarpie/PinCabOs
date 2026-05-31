#!/bin/bash
set -e

export DISPLAY="${DISPLAY:-:0}"

LAYOUT="/opt/pincabos/config/screens/layout.conf"
NAMES="/opt/pincabos/config/screens/screens.env"
LOG="/home/pinball/Share/pincabos-boot-screen-layout-last.log"

{
echo "=== PinCabOS boot screen layout ==="
date
echo "USER=$(whoami)"
echo "DISPLAY=$DISPLAY"
echo "XAUTHORITY=${XAUTHORITY:-}"

if [ ! -f "$LAYOUT" ]; then
  echo "ERREUR: layout absent: $LAYOUT"
  exit 1
fi

. "$LAYOUT"

echo
echo "=== Attendre XRandR disponible ==="
for i in $(seq 1 20); do
  if xrandr --query >/dev/null 2>&1; then
    echo "OK: xrandr prêt après ${i}s"
    break
  fi
  sleep 1
done

if ! xrandr --query >/dev/null 2>&1; then
  echo "ERREUR: xrandr non disponible."
  exit 1
fi

echo
echo "=== xrandr avant ==="
xrandr --query

echo
echo "=== Appliquer layout VPX ==="

if ! xrandr --query | grep -q "^${PLAYFIELD_OUTPUT} connected"; then
  echo "ERREUR: Playfield absent: $PLAYFIELD_OUTPUT"
  xrandr --query | grep " connected" || true
  exit 1
fi

xrandr --output "$PLAYFIELD_OUTPUT" --mode "$PLAYFIELD_MODE" --pos "$PLAYFIELD_POS" --primary

if xrandr --query | grep -q "^${BACKGLASS_OUTPUT} connected"; then
  xrandr --output "$BACKGLASS_OUTPUT" --mode "$BACKGLASS_MODE" --pos "$BACKGLASS_POS"
else
  echo "ATTENTION: Backglass absent: $BACKGLASS_OUTPUT"
fi

if xrandr --query | grep -q "^${DMD_OUTPUT} connected"; then
  xrandr --output "$DMD_OUTPUT" --mode "$DMD_MODE" --pos "$DMD_POS"
else
  echo "ATTENTION: DMD absent: $DMD_OUTPUT"
fi

sleep 1

echo
echo "=== Nommer monitors PinCabOS ==="
if [ -f "$NAMES" ]; then
  . "$NAMES"

  xrandr --delmonitor "$PCO_PLAYFIELD_NAME" 2>/dev/null || true
  xrandr --delmonitor "$PCO_BACKGLASS_NAME" 2>/dev/null || true
  xrandr --delmonitor "$PCO_DMD_NAME" 2>/dev/null || true

  xrandr --setmonitor "$PCO_PLAYFIELD_NAME" "$PCO_PLAYFIELD_GEOMETRY" "$PCO_PLAYFIELD_OUTPUT" || true
  xrandr --setmonitor "$PCO_BACKGLASS_NAME" "$PCO_BACKGLASS_GEOMETRY" "$PCO_BACKGLASS_OUTPUT" || true
  xrandr --setmonitor "$PCO_DMD_NAME" "$PCO_DMD_GEOMETRY" "$PCO_DMD_OUTPUT" || true
fi

echo
echo "=== xrandr après ==="
xrandr --query

echo
echo "=== Monitors nommés ==="
xrandr --listmonitors || true

echo
echo "=== Résumé attendu ==="
echo "ID0 / Playfield : HDMI-0 3840x2160 +0+0 primary"
echo "ID1 / Backglass : DP-1   1920x1080 +3840+0"
echo "ID2 / DMD       : DP-2   1024x768  +5760+0"

} 2>&1 | tee "$LOG"

#!/bin/bash
set -e

export DISPLAY="${DISPLAY:-:0}"

CONF="/opt/pincabos/config/screens/layout.conf"
LOG="/home/pinball/Share/pincabos-x11-layout-last.log"

{
echo "=== PinCabOS X11 layout apply ==="
date
echo "USER=$(whoami)"
echo "DISPLAY=$DISPLAY"

if [ ! -f "$CONF" ]; then
  echo "ERREUR: config absente: $CONF"
  exit 1
fi

. "$CONF"

echo
echo "=== xrandr avant ==="
xrandr --query || exit 1

echo
echo "=== Appliquer layout fixe VPX ==="

if ! xrandr --query | grep -q "^${PLAYFIELD_OUTPUT} connected"; then
  echo "ERREUR: Playfield absent: $PLAYFIELD_OUTPUT"
  echo
  echo "Écrans connectés:"
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
echo "=== xrandr après ==="
xrandr --query

echo
echo "=== Résumé VPX attendu ==="
echo "ID0 / Playfield : $PLAYFIELD_OUTPUT $PLAYFIELD_MODE +$PLAYFIELD_POS primary"
echo "ID1 / Backglass : $BACKGLASS_OUTPUT $BACKGLASS_MODE +$BACKGLASS_POS"
echo "ID2 / DMD       : $DMD_OUTPUT $DMD_MODE +$DMD_POS"

} 2>&1 | tee "$LOG"

#!/bin/bash
set -e

export DISPLAY="${DISPLAY:-:0}"

CONF="/opt/pincabos/config/screens/screens.env"
LOG="/home/pinball/Share/pincabos-named-monitors-last.log"

{
echo "=== PinCabOS Named X11 Monitors ==="
date
echo "USER=$(whoami)"
echo "DISPLAY=$DISPLAY"

if [ ! -f "$CONF" ]; then
  echo "ERREUR: config absente: $CONF"
  exit 1
fi

. "$CONF"

echo
echo "=== xrandr outputs ==="
xrandr --query | grep -E ' connected|primary' || true

echo
echo "=== Nettoyer anciens monitors nommés si présents ==="
xrandr --delmonitor "$PCO_PLAYFIELD_NAME" 2>/dev/null || true
xrandr --delmonitor "$PCO_BACKGLASS_NAME" 2>/dev/null || true
xrandr --delmonitor "$PCO_DMD_NAME" 2>/dev/null || true

echo
echo "=== Créer monitors nommés ==="

if xrandr --query | grep -q "^${PCO_PLAYFIELD_OUTPUT} connected"; then
  xrandr --setmonitor "$PCO_PLAYFIELD_NAME" "$PCO_PLAYFIELD_GEOMETRY" "$PCO_PLAYFIELD_OUTPUT"
  echo "OK: $PCO_PLAYFIELD_NAME -> $PCO_PLAYFIELD_OUTPUT"
else
  echo "ERREUR: output absent: $PCO_PLAYFIELD_OUTPUT"
  exit 1
fi

if xrandr --query | grep -q "^${PCO_BACKGLASS_OUTPUT} connected"; then
  xrandr --setmonitor "$PCO_BACKGLASS_NAME" "$PCO_BACKGLASS_GEOMETRY" "$PCO_BACKGLASS_OUTPUT"
  echo "OK: $PCO_BACKGLASS_NAME -> $PCO_BACKGLASS_OUTPUT"
else
  echo "ATTENTION: output absent: $PCO_BACKGLASS_OUTPUT"
fi

if xrandr --query | grep -q "^${PCO_DMD_OUTPUT} connected"; then
  xrandr --setmonitor "$PCO_DMD_NAME" "$PCO_DMD_GEOMETRY" "$PCO_DMD_OUTPUT"
  echo "OK: $PCO_DMD_NAME -> $PCO_DMD_OUTPUT"
else
  echo "ATTENTION: output absent: $PCO_DMD_OUTPUT"
fi

echo
echo "=== Monitors nommés ==="
xrandr --listmonitors

} 2>&1 | tee "$LOG"

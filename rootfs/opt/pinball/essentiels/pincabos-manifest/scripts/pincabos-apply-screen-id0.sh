#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Apply Screen Layout ID0 ===\e[0m"

set -e

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/var/run/lightdm/root/:0}"

LOG="/home/pinball/Share/pincabos-screen-id0-$(date +%Y%m%d-%H%M%S).txt"
TMP="/tmp/pincabos-xrandr-connected.txt"

echo "=== PinCabOS Screen ID0 Layout ===" | tee "$LOG"
date | tee -a "$LOG"
echo | tee -a "$LOG"

echo "=== 1) xrandr avant ===" | tee -a "$LOG"
xrandr --query | tee -a "$LOG"

echo | tee -a "$LOG"
echo "=== 2) Détection écrans connectés actifs ===" | tee -a "$LOG"

xrandr --query | awk '
/ connected/ {
  name=$1
  current=""
  for (i=1;i<=NF;i++) {
    if ($i ~ /^[0-9]+x[0-9]+\+/) {
      current=$i
      break
    }
  }

  if (current != "") {
    split(current, a, "+")
    split(a[1], r, "x")
    width=r[1]
    height=r[2]
    area=width*height
    print area "|" name "|" width "x" height
  }
}
' | sort -t'|' -k1,1nr > "$TMP"

if [ ! -s "$TMP" ]; then
  echo "ERREUR: aucun écran actif détecté par xrandr." | tee -a "$LOG"
  exit 1
fi

cat "$TMP" | tee -a "$LOG"

echo | tee -a "$LOG"
echo "=== 3) Construire layout : plus gros écran à +0+0 primary ===" | tee -a "$LOG"

XPOS=0
PRIMARY_DONE=0
PREV=""

while IFS='|' read -r AREA NAME MODE; do
  WIDTH="${MODE%x*}"
  HEIGHT="${MODE#*x}"

  if [ "$PRIMARY_DONE" -eq 0 ]; then
    echo "ID0 / PRIMARY: $NAME $MODE +0+0" | tee -a "$LOG"
    xrandr --output "$NAME" --mode "$MODE" --primary --pos 0x0
    PRIMARY_DONE=1
    PREV="$NAME"
    XPOS=$((XPOS + WIDTH))
  else
    echo "Écran suivant: $NAME $MODE +${XPOS}+0" | tee -a "$LOG"
    xrandr --output "$NAME" --mode "$MODE" --pos "${XPOS}x0"
    PREV="$NAME"
    XPOS=$((XPOS + WIDTH))
  fi
done < "$TMP"

sleep 1

echo | tee -a "$LOG"
echo "=== 4) xrandr après ===" | tee -a "$LOG"
xrandr --query | tee -a "$LOG"

echo | tee -a "$LOG"
echo "=== 5) Résumé ID logique attendu VPX ===" | tee -a "$LOG"
echo "ID0 = écran le plus grand, primary, position +0+0" | tee -a "$LOG"
echo "Les autres écrans sont placés à droite, de gauche à droite." | tee -a "$LOG"

echo | tee -a "$LOG"
echo "Log: $LOG"

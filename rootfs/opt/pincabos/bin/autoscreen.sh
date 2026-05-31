#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - AutoScreen universel VPX ===\e[0m"

set -u

export DISPLAY="${DISPLAY:-:0}"

STATE_DIR="/opt/pincabos/config/screens"
LOG="/home/pinball/Share/pincabos-autoscreen-last.log"
TMP="/tmp/pincabos-autoscreen-xrandr.$$"

mkdir -p "$STATE_DIR" /home/pinball/Share

{
echo "=== PinCabOS AutoScreen ==="
date
echo "USER=$(whoami)"
echo "DISPLAY=$DISPLAY"
echo "XAUTHORITY=${XAUTHORITY:-}"

echo
echo "=== 1) Attendre xrandr ==="
READY=0
for i in $(seq 1 25); do
  if xrandr --query >/dev/null 2>&1; then
    READY=1
    echo "OK: xrandr prêt après ${i}s"
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "ERREUR: xrandr non disponible."
  exit 1
fi

echo
echo "=== 2) xrandr avant ==="
xrandr --query

echo
echo "=== 3) Détecter écrans connectés actifs ==="
xrandr --query | awk '
/ connected/ {
  name=$1
  for (i=1;i<=NF;i++) {
    if ($i ~ /^[0-9]+x[0-9]+\+/) {
      split($i, a, "+")
      mode=a[1]
      split(mode, r, "x")
      width=r[1]
      height=r[2]
      area=width*height
      print area "|" name "|" mode "|" width "|" height
      break
    }
  }
}
' | sort -t'|' -k1,1nr > "$TMP"

if [ ! -s "$TMP" ]; then
  echo "ERREUR: aucun écran actif détecté."
  xrandr --query | grep " connected" || true
  exit 1
fi

cat "$TMP"

echo
echo "=== 4) Appliquer layout universel ==="
echo "Règle: plus gros écran = Playfield / ID0 / primary / +0+0"

XPOS=0
IDX=0

cat > "$STATE_DIR/screens-detected.json" <<'JSON'
{
  "screens": [
JSON

while IFS='|' read -r AREA OUTPUT MODE WIDTH HEIGHT; do
  if [ "$IDX" -eq 0 ]; then
    NAME="Playfield"
    POS="${XPOS}x0"
    echo "ID0 / $NAME : $OUTPUT $MODE +$POS primary"
    xrandr --output "$OUTPUT" --mode "$MODE" --pos "$POS" --primary
  elif [ "$IDX" -eq 1 ]; then
    NAME="Backglass"
    POS="${XPOS}x0"
    echo "ID1 / $NAME : $OUTPUT $MODE +$POS"
    xrandr --output "$OUTPUT" --mode "$MODE" --pos "$POS"
  elif [ "$IDX" -eq 2 ]; then
    NAME="DMD"
    POS="${XPOS}x0"
    echo "ID2 / $NAME : $OUTPUT $MODE +$POS"
    xrandr --output "$OUTPUT" --mode "$MODE" --pos "$POS"
  else
    NAME="Screen$IDX"
    POS="${XPOS}x0"
    echo "ID$IDX / $NAME : $OUTPUT $MODE +$POS"
    xrandr --output "$OUTPUT" --mode "$MODE" --pos "$POS"
  fi

  if [ "$IDX" -gt 0 ]; then
    sed -i '$ s/$/,/' "$STATE_DIR/screens-detected.json"
  fi

  cat >> "$STATE_DIR/screens-detected.json" <<JSON
    {
      "id": $IDX,
      "name": "$NAME",
      "output": "$OUTPUT",
      "mode": "$MODE",
      "width": $WIDTH,
      "height": $HEIGHT,
      "area": $AREA,
      "position": "$POS",
      "primary": $([ "$IDX" -eq 0 ] && echo true || echo false)
    }
JSON

  XPOS=$((XPOS + WIDTH))
  IDX=$((IDX + 1))
done < "$TMP"

cat >> "$STATE_DIR/screens-detected.json" <<'JSON'
  ]
}
JSON

sleep 1

echo
echo "=== 5) Nommer monitors XRandR ==="
xrandr --delmonitor Playfield 2>/dev/null || true
xrandr --delmonitor Backglass 2>/dev/null || true
xrandr --delmonitor DMD 2>/dev/null || true
xrandr --delmonitor Screen3 2>/dev/null || true
xrandr --delmonitor Screen4 2>/dev/null || true
xrandr --delmonitor Screen5 2>/dev/null || true

while IFS='|' read -r AREA OUTPUT MODE WIDTH HEIGHT; do
  case "$IDXNAME" in *) true ;; esac
done < /dev/null

COUNT=0
while IFS='|' read -r AREA OUTPUT MODE WIDTH HEIGHT; do
  if [ "$COUNT" -eq 0 ]; then NAME="Playfield"; POSX=0; fi
  if [ "$COUNT" -eq 1 ]; then NAME="Backglass"; fi
  if [ "$COUNT" -eq 2 ]; then NAME="DMD"; fi
  if [ "$COUNT" -gt 2 ]; then NAME="Screen$COUNT"; fi

  POSX="$(awk -v idx="$COUNT" '
    BEGIN {sum=0}
    {
      split($0,a,"|")
      if (NR-1 < idx) sum += a[4]
    }
    END {print sum - a[4]}
  ' "$TMP")"

  GEOM="${WIDTH}/${WIDTH}x${HEIGHT}/${HEIGHT}+${POSX}+0"
  xrandr --setmonitor "$NAME" "$GEOM" "$OUTPUT" 2>/dev/null && echo "OK: $NAME -> $OUTPUT" || true

  COUNT=$((COUNT + 1))
done < "$TMP"

echo
echo "=== 6) Souris à 0,0 ==="
xdotool mousemove 0 0 2>/dev/null && echo "OK: souris déplacée à 0,0" || echo "ATTENTION: xdotool non disponible ou DISPLAY inaccessible"

echo
echo "=== 7) xrandr après ==="
xrandr --query

echo
echo "=== 8) Monitors nommés ==="
xrandr --listmonitors || true

echo
echo "=== 9) State JSON ==="
cat "$STATE_DIR/screens-detected.json"

echo
echo "=== Résumé ==="
echo "ID0 = plus gros écran = Playfield = primary = +0+0"
echo "Souris = 0,0"

rm -f "$TMP"

} 2>&1 | tee "$LOG"

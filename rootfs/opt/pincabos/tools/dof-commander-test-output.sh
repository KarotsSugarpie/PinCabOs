#!/bin/bash
set -e

echo -e "\e[38;5;208m=== DOF COMMANDER OUTPUT ACTION ===\e[0m"

CONTROLLER="${1:-unknown}"
OUTPUT="${2:-0}"
ACTION="${3:-on}"
MODE="${4:-onoff}"
DURATION_MS="${5:-500}"
INTENSITY="${6:-255}"

LOG="/opt/pincabos/logs/dof-commander-test.log"
STAMP="$(date '+%F %T')"

mkdir -p /opt/pincabos/logs

exec > >(tee -a "$LOG") 2>&1

echo "=================================================="
echo "# Modifié $STAMP par PinCabOS fonction(DOF Commander Output Action)"
echo "Controller : $CONTROLLER"
echo "Output local : $OUTPUT"
echo "Action : $ACTION"
echo "Mode : $MODE"
echo "Durée ms : $DURATION_MS"
echo "Intensité : $INTENSITY"
echo "=================================================="

LOWER="$(echo "$CONTROLLER" | tr '[:upper:]' '[:lower:]')"
REAL_DRIVER=""

echo
echo "=== ASSOCIATION TEST ==="
echo "Périphérique demandé : $CONTROLLER"
echo "Sortie locale demandée : $OUTPUT"

if echo "$LOWER" | grep -q "ledwiz"; then
  FAMILY="LedWiz"
  DRIVER_PATH="/opt/pincabos/tools/pincabos-ledwizctl"
elif echo "$LOWER" | grep -q "ws2811"; then
  FAMILY="WS2811 / MX"
  DRIVER_PATH="/opt/pincabos/tools/pincabos-ws2811ctl"
elif echo "$LOWER" | grep -q "dude"; then
  FAMILY="Dude's Cab"
  DRIVER_PATH="/opt/pincabos/tools/pincabos-dudescabctl"
else
  FAMILY="Inconnu"
  DRIVER_PATH=""
fi

echo "Famille détectée : $FAMILY"

if [ -n "$DRIVER_PATH" ] && [ -x "$DRIVER_PATH" ]; then
  REAL_DRIVER="$DRIVER_PATH"
fi

echo
echo "=== ÉTAT DRIVER MATÉRIEL ==="

if [ -z "$REAL_DRIVER" ]; then
  echo "⚠ SIMULATION SEULEMENT — AUCUN SIGNAL ENVOYÉ AU CAB LOCAL."
  echo
  echo "Cause : driver matériel absent pour : $FAMILY"
  echo
  echo "Driver attendu :"
  echo "$DRIVER_PATH"
  echo
  echo "Commande logique reçue :"
  echo "controller='$CONTROLLER' output='$OUTPUT' action='$ACTION' mode='$MODE' duration_ms='$DURATION_MS' intensity='$INTENSITY'"
  echo
  echo "Pour que le test allume vraiment le cab, il faut :"
  echo "1. que le périphérique USB soit visible dans Linux avec lsusb"
  echo "2. que le driver matériel PinCabOS existe"
  echo "3. que le driver reçoive cette sortie locale"
  echo
  echo "Terminé."
  exit 0
fi

echo "Driver matériel utilisé : $REAL_DRIVER"
echo

if ! [[ "$DURATION_MS" =~ ^[0-9]+$ ]]; then
  DURATION_MS=500
fi

if [ "$DURATION_MS" -gt 5000 ]; then
  echo "Durée limitée à 5000 ms pour sécurité."
  DURATION_MS=5000
fi

if ! [[ "$INTENSITY" =~ ^[0-9]+$ ]]; then
  INTENSITY=255
fi

if [ "$INTENSITY" -gt 255 ]; then
  INTENSITY=255
fi

DRY_ARG=""
if [ "${PINCABOS_DOF_DRY_RUN:-0}" = "1" ]; then
  DRY_ARG="--dry-run"
  echo "MODE DRY-RUN GLOBAL ACTIF : aucun signal USB ne sera envoyé."
fi

if [ "$ACTION" = "off" ]; then
  "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action off --mode "$MODE" --duration-ms "$DURATION_MS" --intensity 0 $DRY_ARG $DRY_ARG
  echo "OFF envoyé au driver."
  exit 0
fi

case "$MODE" in
  onoff)
    "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action on --mode "$MODE" --duration-ms "$DURATION_MS" --intensity "$INTENSITY" $DRY_ARG
    sleep "$(awk "BEGIN {print $DURATION_MS/1000}")"
    "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action off --mode "$MODE" --duration-ms "$DURATION_MS" --intensity 0 $DRY_ARG
    ;;
  pulse|strobe|blink)
    STEP_MS=120
    ELAPSED=0
    STATE=0

    while [ "$ELAPSED" -lt "$DURATION_MS" ]; do
      if [ "$STATE" -eq 0 ]; then
        "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action on --mode "$MODE" --duration-ms "$DURATION_MS" --intensity "$INTENSITY" $DRY_ARG
        STATE=1
      else
        "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action off --mode "$MODE" --duration-ms "$DURATION_MS" --intensity 0 $DRY_ARG
        STATE=0
      fi

      sleep "$(awk "BEGIN {print $STEP_MS/1000}")"
      ELAPSED=$((ELAPSED + STEP_MS))
    done

    "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action off --mode "$MODE" --duration-ms "$DURATION_MS" --intensity 0 $DRY_ARG
    ;;
  doublepulse|double|twopulse)
    ELAPSED=0
    CYCLE_MS=500

    while [ "$ELAPSED" -lt "$DURATION_MS" ]; do
      "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action on --mode "$MODE" --duration-ms "$DURATION_MS" --intensity "$INTENSITY" $DRY_ARG
      sleep 0.08
      "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action off --mode "$MODE" --duration-ms "$DURATION_MS" --intensity 0 $DRY_ARG
      sleep 0.08
      "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action on --mode "$MODE" --duration-ms "$DURATION_MS" --intensity "$INTENSITY" $DRY_ARG
      sleep 0.08
      "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action off --mode "$MODE" --duration-ms "$DURATION_MS" --intensity 0 $DRY_ARG
      sleep 0.26

      ELAPSED=$((ELAPSED + CYCLE_MS))
    done

    "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action off --mode "$MODE" --duration-ms "$DURATION_MS" --intensity 0 $DRY_ARG
    ;;
  fadein|fadeout|sine)
    "$REAL_DRIVER" --controller "$CONTROLLER" --output "$OUTPUT" --action on --mode "$MODE" --duration-ms "$DURATION_MS" --intensity "$INTENSITY" $DRY_ARG
    ;;
  *)
    echo "Mode inconnu : $MODE"
    exit 1
    ;;
esac

echo
echo "Commande matérielle terminée."

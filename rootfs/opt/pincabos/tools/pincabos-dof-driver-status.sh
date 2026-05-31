#!/bin/bash
set -e

echo -e "\e[38;5;208m=== PINCABOS DOF DRIVER STATUS ===\e[0m"

echo
echo "=== USB DEVICES ==="
lsusb || true

echo
echo "=== HIDRAW ==="
ls -l /dev/hidraw* 2>/dev/null || echo "Aucun hidraw"

echo
echo "=== SERIAL ==="
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "Aucun serial USB"

echo
echo "=== DETECTION FAMILLES ==="
USB="$(lsusb 2>/dev/null | tr '[:upper:]' '[:lower:]')"

detect_vendor() {
  local label="$1"
  local regex="$2"

  if echo "$USB" | grep -Eiq "$regex"; then
    echo "OK     $label détecté"
  else
    echo "ABSENT $label non détecté"
  fi
}

detect_vendor "Ledwiz" "fafa|ledwiz|groovy"
detect_vendor "Ultimarc / PacDrive / PacLed / UltimateIO" "d209|ultimarc|pacdrive|pacled"
detect_vendor "FRDM-KL25Z / Pinscape" "15a2|1fc9|freescale|nxp|kl25z|pinscape"
detect_vendor "PinscapePico / RP2040" "2e8a|1209|raspberry|rp2040|pico"
detect_vendor "FTDI" "0403|ftdi"
detect_vendor "Arduino" "2341|2a03|1b4f|arduino"
detect_vendor "ESP / Wemos / CH340 / CP210x" "1a86|10c4|303a|wch|silicon labs|espressif"

echo
echo "=== MODULES PINCABOS ==="
for f in \
  pincabos-ledwizctl \
  pincabos-pinscapectl \
  pincabos-pinonectl \
  pincabos-ultimarcctl \
  pincabos-ws2811ctl \
  pincabos-sainsmartctl \
  pincabos-huectl \
  pincabos-pinctl \
  pincabos-dudescabctl \
  pincabos-artnetctl \
  pincabos-pinscape-picoctl
do
  if [ -x "/opt/pincabos/tools/$f" ]; then
    echo "OK     /opt/pincabos/tools/$f"
  else
    echo "TODO   /opt/pincabos/tools/$f"
  fi
done

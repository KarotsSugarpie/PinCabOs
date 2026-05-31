#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Check AutoScreen VPX ===\e[0m"

echo
echo "=== Scripts ==="
ls -lah /opt/pincabos/bin/autoscreen.sh
ls -lah /opt/pinball/essentiels/pincabos-manifest/scripts/autoscreen.sh

echo
echo "=== Service systemd ==="
systemctl status pincabos-screen-layout.service --no-pager -l | sed -n '1,35p' || true

echo
echo "=== XRandR actuel ==="
sudo -u pinball DISPLAY=:0 xrandr --query | grep -E ' connected|primary' || true

echo
echo "=== Monitors nommés ==="
sudo -u pinball DISPLAY=:0 xrandr --listmonitors || true

echo
echo "=== State JSON ==="
cat /opt/pincabos/config/screens/screens-detected.json 2>/dev/null || echo "Aucun state JSON."

echo
echo "=== Souris ==="
DISPLAY=:0 xdotool getmouselocation 2>/dev/null || true

echo
echo "=== Validation ID0 ==="
XR="$(sudo -u pinball DISPLAY=:0 xrandr --query)"
PRIMARY_LINE="$(echo "$XR" | grep ' connected primary' | head -n 1 || true)"

if [ -n "$PRIMARY_LINE" ]; then
  echo "Primary actuel:"
  echo "$PRIMARY_LINE"

  if echo "$PRIMARY_LINE" | grep -q '+0+0'; then
    echo "OK: primary est à +0+0"
  else
    echo "ERREUR: primary n'est pas à +0+0"
  fi
else
  echo "ERREUR: aucun primary détecté."
fi

#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Check écrans nommés ===\e[0m"

echo
echo "=== Mapping PinCabOS ==="
cat /opt/pincabos/config/screens/screens.env

echo
echo "=== XRandR connected ==="
sudo -u pinball DISPLAY=:0 xrandr --query | grep -E ' connected|primary'

echo
echo "=== XRandR monitors ==="
sudo -u pinball DISPLAY=:0 xrandr --listmonitors

echo
echo "=== Attendu ==="
echo "Playfield -> HDMI-0 -> ID0 -> 3840x2160+0+0 primary"
echo "Backglass -> DP-1  -> ID1 -> 1920x1080+3840+0"
echo "DMD       -> DP-2  -> ID2 -> 1024x768+5760+0"

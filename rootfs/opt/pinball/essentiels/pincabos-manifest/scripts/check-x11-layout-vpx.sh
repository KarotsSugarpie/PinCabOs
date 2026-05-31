#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Check X11 layout VPX ===\e[0m"

echo
echo "=== Process X11 ==="
ps -ef | grep -Ei 'lightdm|Xorg|openbox' | grep -v grep || true

echo
echo "=== xrandr comme pinball ==="
sudo -u pinball DISPLAY=:0 xrandr --query

echo
echo "=== Résumé actuel ==="
sudo -u pinball DISPLAY=:0 xrandr --query | grep -E ' connected|primary'

echo
echo "=== Résumé attendu VPX ==="
echo "HDMI-0 connected primary 3840x2160+0+0"
echo "DP-1   connected 1920x1080+3840+0"
echo "DP-2   connected 1024x768+5760+0"

echo
echo "=== Validation automatique ==="
XR="$(sudo -u pinball DISPLAY=:0 xrandr --query)"

echo "$XR" | grep -q "HDMI-0 connected primary 3840x2160+0+0" && echo "OK: Playfield ID0 HDMI-0" || echo "ERREUR: HDMI-0 pas en ID0"
echo "$XR" | grep -q "DP-1 connected 1920x1080+3840+0" && echo "OK: Backglass DP-1" || echo "ERREUR: DP-1 mauvais placement"
echo "$XR" | grep -q "DP-2 connected 1024x768+5760+0" && echo "OK: DMD DP-2" || echo "ERREUR: DP-2 mauvais placement"

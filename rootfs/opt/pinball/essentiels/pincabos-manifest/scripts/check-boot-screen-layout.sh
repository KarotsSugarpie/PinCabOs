#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Check boot screen layout VPX ===\e[0m"

echo
echo "=== Service systemd ==="
systemctl status pincabos-screen-layout.service --no-pager -l | sed -n '1,30p' || true

echo
echo "=== LightDM config ==="
cat /etc/lightdm/lightdm.conf.d/40-pincabos-display-setup.conf
cat /etc/lightdm/lightdm.conf.d/50-pincabos-x11.conf

echo
echo "=== XRandR actuel ==="
sudo -u pinball DISPLAY=:0 xrandr --query | grep -E ' connected|primary'

echo
echo "=== Monitors nommés ==="
sudo -u pinball DISPLAY=:0 xrandr --listmonitors || true

echo
echo "=== Validation ==="
XR="$(sudo -u pinball DISPLAY=:0 xrandr --query)"

echo "$XR" | grep -q "HDMI-0 connected primary 3840x2160+0+0" && echo "OK: ID0 Playfield HDMI-0" || echo "ERREUR: HDMI-0 pas ID0/primary"
echo "$XR" | grep -q "DP-1 connected 1920x1080+3840+0" && echo "OK: ID1 Backglass DP-1" || echo "ERREUR: DP-1 mauvais placement"
echo "$XR" | grep -q "DP-2 connected 1024x768+5760+0" && echo "OK: ID2 DMD DP-2" || echo "ERREUR: DP-2 mauvais placement"

echo
echo "=== Logs ==="
ls -lah /home/pinball/Share/pincabos-*screen* /home/pinball/Share/pincabos-*layout* 2>/dev/null || true

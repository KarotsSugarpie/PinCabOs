#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Installer dépendances VPX/B2S/DOF/VPXTools/PuP ===\e[0m"

set -e

LOG="/home/pinball/Share/vpx-stack-deps-$(date +%Y%m%d-%H%M%S).txt"
PKG="/opt/pinball/essentiels/pincabos-manifest/pincabos-essential-packages.txt"

mkdir -p /home/pinball/Share

{
echo "=== PinCabOS - VPX stack dependencies ==="
date

echo
echo "=== 1) Update APT ==="
apt update

echo
echo "=== 2) Installer dépendances depuis manifest ==="
grep -vE '^\s*#|^\s*$' "$PKG" > /tmp/pincabos-all-essential-packages.txt

DEBIAN_FRONTEND=noninteractive apt install -y $(cat /tmp/pincabos-all-essential-packages.txt)

echo
echo "=== 3) Groupes pinball pour USB/input/audio/video ==="
usermod -aG video,audio,input,plugdev,render,dialout pinball

echo
echo "=== 4) Créer dossiers VPX/B2S/DOF/PuP standards ==="
mkdir -p \
  /opt/pincabos/apps/vpx \
  /opt/pincabos/apps/frontend \
  /opt/pincabos/apps/dof \
  /opt/pincabos/apps/vpxtools \
  /opt/pincabos/bin \
  /opt/pincabos/config/vpx \
  /opt/pincabos/config/dof \
  /home/pinball/.local/share/VPinballX/10.8 \
  /home/pinball/.vpinball \
  /home/pinball/Tables \
  /home/pinball/PinMAME/roms \
  /home/pinball/PinMAME/cfg \
  /home/pinball/PinMAME/nvram \
  /home/pinball/PupVideos \
  /home/pinball/Share

chown -R pinball:pinball \
  /home/pinball/.local \
  /home/pinball/.vpinball \
  /home/pinball/Tables \
  /home/pinball/PinMAME \
  /home/pinball/PupVideos \
  /home/pinball/Share

echo
echo "=== 5) Vérifications clés ==="
for cmd in glxinfo vulkaninfo ffmpeg mpv python3 pip3 git cmake ninja xrandr evtest; do
  printf "%-18s : " "$cmd"
  command -v "$cmd" || true
done

echo
echo "=== 6) NVIDIA/X11 rapide ==="
nvidia-smi || true
sudo -u pinball DISPLAY=:0 glxinfo -B | grep -Ei 'OpenGL vendor|OpenGL renderer|OpenGL version' || true
sudo -u pinball DISPLAY=:0 xrandr --query | grep -E ' connected|primary' || true

echo
echo "=== Services systemd ==="
if systemctl --failed --no-pager --quiet; then
  echo "OK: aucun service failed."
else
  systemctl --failed --no-pager
fi

echo
echo "=== OK ==="

} 2>&1 | tee "$LOG"

chown pinball:pinball "$LOG" 2>/dev/null || true
echo
echo "Log: $LOG"

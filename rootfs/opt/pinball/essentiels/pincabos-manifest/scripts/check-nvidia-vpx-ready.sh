#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Check NVIDIA final avant VPX ===\e[0m"

echo
echo "=== 1) Driver kernel ==="
lsmod | grep -Ei 'nvidia|nouveau|nova' || true
lspci -k | grep -A6 -Ei 'vga|3d|display'

echo
echo "=== 2) NVIDIA SMI ==="
nvidia-smi || echo "ERREUR: nvidia-smi ne fonctionne pas"

echo
echo "=== 3) OpenGL comme pinball ==="
sudo -u pinball DISPLAY=:0 glxinfo -B || echo "ERREUR: glxinfo"

echo
echo "=== 4) Vulkan ==="
sudo -u pinball DISPLAY=:0 vulkaninfo --summary 2>/dev/null || vulkaninfo --summary 2>/dev/null || echo "ERREUR: vulkaninfo"

echo
echo "=== 5) Écrans ==="
sudo -u pinball DISPLAY=:0 xrandr --query || echo "ERREUR: xrandr"

echo
echo "=== 6) Résumé attendu ==="
echo "OK attendu:"
echo "  Kernel driver in use: nvidia"
echo "  OpenGL vendor string: NVIDIA Corporation"
echo "  OpenGL renderer string: NVIDIA GeForce RTX 3060 Ti"
echo "  nouveau absent"
echo "  nvidia-smi fonctionne"

echo
echo "=== Services systemd ==="
if systemctl --failed --no-pager --quiet; then
  echo "OK: aucun service failed."
else
  systemctl --failed --no-pager
fi

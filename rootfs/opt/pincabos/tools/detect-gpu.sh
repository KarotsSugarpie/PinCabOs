#!/bin/bash

echo "=================================================="
echo " PinCabOs - Détection GPU"
echo "=================================================="
echo

echo "[GPU PCI]"
lspci -nnk | grep -A4 -Ei "vga|3d|display" || true

echo
echo "[Modules chargés]"
lsmod | grep -Ei "nvidia|amdgpu|radeon|i915|nouveau" || true

echo
echo "[OpenGL]"
if command -v glxinfo >/dev/null 2>&1; then
  glxinfo -B 2>/dev/null || true
else
  echo "glxinfo non installé"
fi

echo
echo "[Vulkan]"
if command -v vulkaninfo >/dev/null 2>&1; then
  vulkaninfo --summary 2>/dev/null || true
else
  echo "vulkaninfo non installé"
fi

echo
echo "[Écrans XRandR]"
DISPLAY=:0 XAUTHORITY=/home/pinball/.Xauthority xrandr --query 2>/dev/null || true

#!/bin/bash
set -e

LOG="/opt/pincabos/logs/updates/update-gpu-drivers-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=================================================="
echo " PinCabOs - Mise à jour pilotes GPU"
echo " Log: $LOG"
echo "=================================================="

apt update
apt install -y pciutils mesa-utils vulkan-tools x11-xserver-utils ubuntu-drivers-common linux-firmware

GPU_INFO="$(lspci -nn | grep -Ei 'vga|3d|display' || true)"

echo "$GPU_INFO"

if echo "$GPU_INFO" | grep -qi "NVIDIA"; then
  echo
  echo "GPU NVIDIA détecté."
  echo "Installation recommandée via ubuntu-drivers autoinstall..."
  ubuntu-drivers devices || true
  ubuntu-drivers autoinstall || true

  echo "Installation outils NVIDIA..."
  apt install -y nvidia-settings nvidia-prime || true

elif echo "$GPU_INFO" | grep -qiE "AMD|ATI|Advanced Micro Devices"; then
  echo
  echo "GPU AMD détecté."
  echo "Installation stack AMD open-source Mesa/Vulkan..."
  apt install -y \
    mesa-vulkan-drivers \
    mesa-utils \
    libgl1-mesa-dri \
    xserver-xorg-video-amdgpu \
    linux-firmware \
    vulkan-tools

elif echo "$GPU_INFO" | grep -qiE "Intel"; then
  echo
  echo "GPU Intel détecté."
  echo "Installation stack Intel Mesa/Vulkan..."
  apt install -y \
    mesa-vulkan-drivers \
    mesa-utils \
    libgl1-mesa-dri \
    linux-firmware \
    vulkan-tools

else
  echo
  echo "Aucun GPU NVIDIA/AMD/Intel clairement détecté."
  echo "Installation stack Mesa générique..."
  apt install -y mesa-vulkan-drivers mesa-utils libgl1-mesa-dri linux-firmware vulkan-tools
fi

echo
echo "=================================================="
echo " Vérification après installation"
echo "=================================================="

lspci -nnk | grep -A4 -Ei "vga|3d|display" || true
lsmod | grep -Ei "nvidia|amdgpu|radeon|i915|nouveau" || true

echo
echo "Mise à jour GPU terminée."
echo "Un reboot est recommandé après changement de pilote GPU."
echo "=================================================="

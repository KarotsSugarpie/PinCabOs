#!/bin/bash
# PinCabOs-File created by Karots Sugarpie
set -Eeuo pipefail

LOG_DIR="/opt/pincabos/logs/updates"
STATE_DIR="/opt/pincabos/state"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="${LOG_DIR}/update-gpu-drivers-${TS}.log"

mkdir -p "$LOG_DIR" "$STATE_DIR"

exec > >(tee -a "$LOG") 2>&1

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: $0"
  echo "Installe/met à jour les pilotes GPU PinCabOS et marque un reboot requis."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

wait_apt_locks() {
  local waited=0
  local max_wait="${PCO_APT_LOCK_MAX_WAIT:-600}"

  while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock /var/lib/apt/lists/lock >/dev/null 2>&1; do
    if [ "$waited" -ge "$max_wait" ]; then
      echo "NOGOOD: locks apt/dpkg encore actifs après ${max_wait}s."
      echo "Processus apt/dpkg détectés:"
      ps aux | grep -Ei 'apt|dpkg|unattended|packagekit' | grep -v grep || true
      return 1
    fi

    echo "Attente lock apt/dpkg... ${waited}s/${max_wait}s"
    ps aux | grep -Ei 'apt|dpkg|unattended|packagekit' | grep -v grep || true
    sleep 5
    waited=$((waited + 5))
  done

  return 0
}

apt_update_safe() {
  wait_apt_locks
  apt-get update
}

apt_install_safe() {
  wait_apt_locks
  apt-get install -y \
    -o Dpkg::Options::="--force-confnew" \
    -o Dpkg::Options::="--force-confdef" \
    "$@"
}

echo "=================================================="
echo " PinCabOS - Mise à jour pilotes GPU"
echo " Log: $LOG"
echo " Début: $(date)"
echo "=================================================="
echo

echo "=== 1) Préparation apt ==="
apt_update_safe

echo
echo "=== 2) Installation outils GPU de base ==="
apt_install_safe \
  pciutils \
  mesa-utils \
  vulkan-tools \
  x11-xserver-utils \
  ubuntu-drivers-common \
  linux-firmware

echo
echo "=== 3) Détection GPU PCI ==="
GPU_INFO="$(lspci -Dnn | grep -Ei 'VGA compatible controller|3D controller|Display controller' || true)"
echo "$GPU_INFO"

HAS_NVIDIA=0
HAS_AMD=0
HAS_INTEL=0
HAS_VIRTIO=0

echo "$GPU_INFO" | grep -Eqi '\[10de:' && HAS_NVIDIA=1
echo "$GPU_INFO" | grep -Eqi '\[(1002|1022):' && HAS_AMD=1
echo "$GPU_INFO" | grep -Eqi '\[8086:' && HAS_INTEL=1
echo "$GPU_INFO" | grep -Eqi '\[1af4:' && HAS_VIRTIO=1

echo
echo "Familles détectées:"
echo "NVIDIA [10de]  : $HAS_NVIDIA"
echo "AMD/ATI [1002/1022] : $HAS_AMD"
echo "Intel [8086]   : $HAS_INTEL"
echo "Virtio [1af4]  : $HAS_VIRTIO"

echo
echo "=== 4) Installation stack selon GPU ==="

if [ "$HAS_NVIDIA" = "1" ]; then
  echo "GPU NVIDIA détecté par vendor-id."
  echo "Installation recommandée via ubuntu-drivers autoinstall..."
  ubuntu-drivers devices || true
  ubuntu-drivers autoinstall || true

  echo "Installation outils NVIDIA..."
  apt_install_safe \
    nvidia-settings \
    nvidia-prime || true
fi

if [ "$HAS_AMD" = "1" ]; then
  echo "GPU AMD/ATI détecté par vendor-id."
  echo "Installation stack AMD open-source Mesa/Vulkan..."
  apt_install_safe \
    mesa-vulkan-drivers \
    mesa-utils \
    libgl1-mesa-dri \
    xserver-xorg-video-amdgpu \
    xserver-xorg-video-radeon \
    linux-firmware \
    vulkan-tools || true
fi

if [ "$HAS_INTEL" = "1" ]; then
  echo "GPU Intel détecté par vendor-id."
  echo "Installation stack Intel Mesa/Vulkan."
  apt_install_safe \
    mesa-vulkan-drivers \
    mesa-utils \
    libgl1-mesa-dri \
    linux-firmware \
    vulkan-tools || true
fi

if [ "$HAS_VIRTIO" = "1" ]; then
  echo "GPU Virtio/VM détecté par vendor-id."
  echo "Installation stack Mesa générique VM."
  apt_install_safe \
    mesa-vulkan-drivers \
    mesa-utils \
    libgl1-mesa-dri \
    linux-firmware \
    vulkan-tools || true
fi

if [ "$HAS_NVIDIA" = "0" ] && [ "$HAS_AMD" = "0" ] && [ "$HAS_INTEL" = "0" ] && [ "$HAS_VIRTIO" = "0" ]; then
  echo "Aucun GPU NVIDIA/AMD/Intel/Virtio clairement détecté."
  echo "Installation stack Mesa générique..."
  apt_install_safe \
    mesa-vulkan-drivers \
    mesa-utils \
    libgl1-mesa-dri \
    linux-firmware \
    vulkan-tools || true
fi

echo
echo "=== 5) Vérification après installation ==="
lspci -nnk | grep -A4 -Ei "vga|3d|display" || true
echo
lsmod | grep -Ei "nvidia|amdgpu|radeon|i915|xe|nouveau|virtio_gpu|qxl|vmwgfx" || true
echo

echo "=== 6) Flags PinCabOS ==="
date -Is > "${STATE_DIR}/gpu-update-last-success.flag"
date -Is > "${STATE_DIR}/gpu-update-required-reboot.flag"
chown -R pinball:pinball "$STATE_DIR" 2>/dev/null || true

echo "OK: ${STATE_DIR}/gpu-update-last-success.flag"
echo "OK: ${STATE_DIR}/gpu-update-required-reboot.flag"

echo
echo "=================================================="
echo " ✅ Driver GPU installé avec succès."
echo " 🔄 PinCabOS doit maintenant redémarrer pour activer le driver."
echo "=================================================="
echo

for i in 10 9 8 7 6 5 4 3 2 1; do
  echo "Redémarrage automatique dans ${i} seconde(s)..."
  sleep 1
done

echo
echo "Redémarrage maintenant."
echo "Fin avant reboot: $(date)"
sync

if command -v systemctl >/dev/null 2>&1; then
  systemctl reboot -i
else
  /sbin/reboot
fi

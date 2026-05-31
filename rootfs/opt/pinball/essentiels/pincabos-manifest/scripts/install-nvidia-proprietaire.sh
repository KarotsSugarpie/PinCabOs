#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Installer NVIDIA propriétaire pour VPX ===\e[0m"

set -e

LOG="/home/pinball/Share/nvidia-force-install-$(date +%Y%m%d-%H%M%S).txt"
MANIFEST="/opt/pinball/essentiels/pincabos-manifest"
mkdir -p /home/pinball/Share

{
echo "=== PinCabOS - NVIDIA propriétaire install ==="
date

echo
echo "=== 1) État avant install ==="
lspci -k | grep -A6 -Ei 'vga|3d|display' || true
lsmod | grep -Ei 'nouveau|nvidia|nova' || true
command -v nvidia-smi || true

echo
echo "=== 2) Update + outils ==="
apt update
apt install -y ubuntu-drivers-common dkms build-essential linux-headers-$(uname -r) linux-headers-generic

echo
echo "=== 3) Détection Ubuntu drivers ==="
ubuntu-drivers devices || true

echo
echo "=== 4) Paquets NVIDIA disponibles ==="
apt-cache search '^nvidia-driver-[0-9]+' | sort || true

echo
echo "=== 5) Choisir driver NVIDIA disponible ==="
DRIVER=""

for CANDIDATE in nvidia-driver-580 nvidia-driver-575 nvidia-driver-570 nvidia-driver-565 nvidia-driver-560 nvidia-driver-555 nvidia-driver-550 nvidia-driver-535; do
  if apt-cache show "$CANDIDATE" >/dev/null 2>&1; then
    DRIVER="$CANDIDATE"
    break
  fi
done

if [ -z "$DRIVER" ]; then
  echo "ERREUR: aucun paquet nvidia-driver connu trouvé."
  apt-cache search nvidia-driver || true
  exit 1
fi

echo "Driver choisi: $DRIVER"

echo
echo "=== 6) Installer driver NVIDIA ==="
DEBIAN_FRONTEND=noninteractive apt install -y "$DRIVER"

echo
echo "=== 7) Appliquer blacklist nouveau ==="
cp -f "$MANIFEST/config/blacklist-nouveau-pincabos.conf" /etc/modprobe.d/blacklist-nouveau-pincabos.conf
cp -f "$MANIFEST/config/nvidia-drm-pincabos.conf" /etc/modprobe.d/nvidia-drm-pincabos.conf
cp -f "$MANIFEST/config/nvidia-modules-load.conf" /etc/modules-load.d/nvidia-pincabos.conf

echo
echo "=== 8) Sauver driver choisi dans manifest ==="
echo "$DRIVER" > "$MANIFEST/nvidia-driver-selected.txt"
dpkg -l | grep -Ei 'nvidia-driver|nvidia-dkms|nvidia-utils|libnvidia' > "$MANIFEST/nvidia-packages-installed.txt" || true

echo
echo "=== 9) Rebuild initramfs + grub ==="
update-initramfs -u
update-grub

echo
echo "=== Services systemd ==="
if systemctl --failed --no-pager --quiet; then
  echo "OK: aucun service failed."
else
  systemctl --failed --no-pager
fi

echo
echo "=== OK ==="
echo "REBOOT OBLIGATOIRE:"
echo "reboot"

} 2>&1 | tee "$LOG"

chown pinball:pinball "$LOG" 2>/dev/null || true

echo
echo "Log sauvegardé:"
echo "$LOG"

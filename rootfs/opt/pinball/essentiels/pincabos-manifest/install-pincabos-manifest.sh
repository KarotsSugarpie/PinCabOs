#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Installer depuis /opt/pinball/essentiels/pincabos-manifest ===\e[0m"

set -euo pipefail

MANIFEST_DIR="/opt/pinball/essentiels/pincabos-manifest"

if [ "$EUID" -ne 0 ]; then
  echo "ERREUR: lance ce script en root."
  exit 1
fi

if [ ! -d "$MANIFEST_DIR" ]; then
  echo "ERREUR: dossier absent: $MANIFEST_DIR"
  exit 1
fi

echo
echo "=== 1) Restaurer dépôts APT ==="
mkdir -p /etc/apt/sources.list.d
mkdir -p /etc/apt/keyrings

if [ -f "$MANIFEST_DIR/apt-sources.list" ]; then
  cp -a /etc/apt/sources.list "/etc/apt/sources.list.backup-pincabos-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
  cp -a "$MANIFEST_DIR/apt-sources.list" /etc/apt/sources.list
fi

if [ -d "$MANIFEST_DIR/apt-sources.d" ]; then
  cp -a "$MANIFEST_DIR/apt-sources.d/." /etc/apt/sources.list.d/
fi

if [ -d "$MANIFEST_DIR/apt-keyrings" ]; then
  cp -a "$MANIFEST_DIR/apt-keyrings/." /etc/apt/keyrings/
  chmod 0644 /etc/apt/keyrings/* 2>/dev/null || true
fi

echo
echo "=== 2) Update APT ==="
apt update

echo
echo "=== 3) Installer paquets essentiels ==="
PKG_FILE="$MANIFEST_DIR/pincabos-essential-packages.txt"

if [ ! -f "$PKG_FILE" ]; then
  echo "ERREUR: fichier absent: $PKG_FILE"
  exit 1
fi

grep -vE '^\s*#|^\s*$' "$PKG_FILE" > /tmp/pincabos-essential-packages.txt
DEBIAN_FRONTEND=noninteractive apt install -y $(cat /tmp/pincabos-essential-packages.txt)

echo
echo "=== 4) Créer utilisateur pinball si absent ==="
if ! id pinball >/dev/null 2>&1; then
  useradd -m -s /bin/bash pinball
  echo "Utilisateur pinball créé. Définis son mot de passe avec: passwd pinball"
else
  echo "Utilisateur pinball déjà présent."
fi

echo
echo "=== 5) Groupes pinball ==="
usermod -aG video,audio,input,plugdev,render,dialout pinball

echo
echo "=== 6) Dossiers standards ==="
mkdir -p \
  /opt/pincabos/bin \
  /opt/pincabos/apps/vpx \
  /opt/pincabos/apps/frontend \
  /opt/pincabos/apps/dof \
  /opt/pincabos/config \
  /opt/pincabos/web \
  /opt/pincabos/backups \
  /opt/pinball/essentiels/pincabos-manifest \
  /home/pinball/Share \
  /home/pinball/Tables \
  /home/pinball/.local/share/VPinballX/10.8

chown -R pinball:pinball \
  /home/pinball/Share \
  /home/pinball/Tables \
  /home/pinball/.local

echo
echo "=== 7) Session X11 PinCabOS ==="
mkdir -p /usr/share/xsessions

cat > /usr/share/xsessions/pincabos-openbox.desktop <<'EODESKTOP'
[Desktop Entry]
Name=PinCabOS Openbox X11
Comment=PinCabOS X11 session for VPX
Exec=openbox-session
Type=Application
DesktopNames=Openbox
EODESKTOP

mkdir -p /etc/lightdm/lightdm.conf.d

cat > /etc/lightdm/lightdm.conf.d/50-pincabos-x11.conf <<'EOLIGHTDM'
[Seat:*]
autologin-user=pinball
autologin-user-timeout=0
user-session=pincabos-openbox
greeter-session=lightdm-gtk-greeter
EOLIGHTDM

mkdir -p /home/pinball/.config/openbox

cat > /home/pinball/.config/openbox/autostart <<'EOAUTO'
#!/bin/sh

xset -dpms
xset s off
xset s noblank
xsetroot -solid black

xterm -geometry 120x35+40+40 -title "PinCabOS Debug Console" &
EOAUTO

chown -R pinball:pinball /home/pinball/.config
chmod +x /home/pinball/.config/openbox/autostart

echo
echo "=== 8) Activer LightDM ==="
systemctl enable lightdm
echo
echo "=== Configs NVIDIA / nouveau pour VPX ==="
if [ -d "/opt/pinball/essentiels/pincabos-manifest/config" ]; then
  cp -f /opt/pinball/essentiels/pincabos-manifest/config/blacklist-nouveau-pincabos.conf /etc/modprobe.d/blacklist-nouveau-pincabos.conf 2>/dev/null || true
  cp -f /opt/pinball/essentiels/pincabos-manifest/config/nvidia-drm-pincabos.conf /etc/modprobe.d/nvidia-drm-pincabos.conf 2>/dev/null || true
  cp -f /opt/pinball/essentiels/pincabos-manifest/config/nvidia-modules-load.conf /etc/modules-load.d/nvidia-pincabos.conf 2>/dev/null || true
fi

systemctl set-default graphical.target

echo
echo "=== 9) Vérification ==="
for cmd in Xorg openbox-session lightdm xrandr glxinfo vulkaninfo python3 pip3 git ffmpeg evtest lsusb nginx ttyd google-chrome; do
  printf "%-22s : " "$cmd"
  command -v "$cmd" || true
done

echo
echo "--- Services failed ---"
systemctl --failed --no-pager

echo
echo "=== OK ==="
echo "Reboot recommandé: reboot"

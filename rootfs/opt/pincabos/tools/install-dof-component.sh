#!/bin/bash
set -e

echo -e "\e[38;5;208m=== INSTALLATION COMPOSANT DOF PINCABOS ===\e[0m"

COMPONENT="${1:-all}"
LOG="/opt/pincabos/logs/dof-component-install.log"
UDEV="/etc/udev/rules.d/99-pincabos-dof-controllers.rules"
STAMP="$(date '+%F %T')"

mkdir -p /opt/pincabos/logs
mkdir -p /opt/pincabos/config/dof
mkdir -p /opt/pincabos/backups/dof

exec > >(tee -a "$LOG") 2>&1

echo "=================================================="
echo "# Modifié $STAMP par PinCabOS fonction(DOF Component Install: $COMPONENT)"
echo "Composant demandé : $COMPONENT"
echo "=================================================="

install_common() {
  echo
  echo "[COMMON] Installation outils communs USB / HID / Serial"
  apt update
  apt install -y \
    usbutils \
    pciutils \
    udev \
    libusb-1.0-0 \
    libusb-1.0-0-dev \
    libudev-dev \
    libhidapi-hidraw0 \
    libhidapi-libusb0 \
    libhidapi-dev \
    hidapi-tools \
    python3 \
    python3-pip \
    python3-venv \
    python3-serial \
    python3-usb \
    evtest \
    joystick \
    jstest-gtk \
    input-utils \
    setserial \
    screen \
    minicom \
    picocom \
    git \
    curl \
    wget \
    build-essential \
    cmake \
    pkg-config

  groupadd -f plugdev
  groupadd -f input
  usermod -aG dialout,plugdev,input pinball || true
}

install_ledwiz() {
  echo
  echo "[LedWiz32] libusb / hidraw / udev"
  apt install -y libusb-1.0-0 libusb-1.0-0-dev hidapi-tools libhidapi-hidraw0 libhidapi-dev
  modprobe usbhid 2>/dev/null || true
}

install_pinscape_kl25z() {
  echo
  echo "[Pinscape KL25Z / NXP] HID / libusb / udev"
  apt install -y libusb-1.0-0 libusb-1.0-0-dev hidapi-tools libhidapi-hidraw0 libhidapi-dev
  modprobe usbhid 2>/dev/null || true
}

install_pinscape_pico() {
  echo
  echo "[Pinscape Pico / RP2040] HID / serial / udev"
  apt install -y libusb-1.0-0 libusb-1.0-0-dev hidapi-tools libhidapi-hidraw0 libhidapi-dev python3-serial
  modprobe usbhid 2>/dev/null || true
  modprobe cdc_acm 2>/dev/null || true
}

install_dudes_esp() {
  echo
  echo "[Dude's Cab / Wemos / ESP] CH340 / CP210x / ESP serial"
  apt install -y python3-serial screen minicom picocom
  modprobe usbserial 2>/dev/null || true
  modprobe ch341 2>/dev/null || true
  modprobe cp210x 2>/dev/null || true
  modprobe cdc_acm 2>/dev/null || true
}

install_pacled() {
  echo
  echo "[PacLed / Ultimarc] HID / libusb / udev"
  apt install -y libusb-1.0-0 libusb-1.0-0-dev hidapi-tools libhidapi-hidraw0 libhidapi-dev
  modprobe usbhid 2>/dev/null || true
}

install_ftdi() {
  echo
  echo "[FTDI] ftdi_sio / serial"
  apt install -y python3-serial screen minicom picocom setserial
  modprobe usbserial 2>/dev/null || true
  modprobe ftdi_sio 2>/dev/null || true
}

install_arduino() {
  echo
  echo "[Arduino / Leonardo / Micro] cdc_acm / HID"
  apt install -y python3-serial screen minicom picocom
  modprobe cdc_acm 2>/dev/null || true
  modprobe usbhid 2>/dev/null || true
}

install_serial_usb() {
  echo
  echo "[Serial USB] usbserial / cdc_acm / ch341 / cp210x / ftdi_sio"
  apt install -y python3-serial screen minicom picocom setserial
  modprobe usbserial 2>/dev/null || true
  modprobe cdc_acm 2>/dev/null || true
  modprobe ch341 2>/dev/null || true
  modprobe cp210x 2>/dev/null || true
  modprobe ftdi_sio 2>/dev/null || true
}

write_udev_rules() {
  echo
  echo "[UDEV] Écriture règles DOF PinCabOS"

  if [ -f "$UDEV" ]; then
    cp -av "$UDEV" "/opt/pincabos/backups/dof/99-pincabos-dof-controllers.rules.backup-$(date +%Y%m%d-%H%M%S)" || true
  fi

  cat > "$UDEV" <<EOF2
# Modifié $(date '+%F %T') par PinCabOS fonction(DOF Component Install: $COMPONENT)
# PinCabOS DOF / Feedback controllers

# LedWiz / GroovyGameGear - Vendor ID connu : FAFA
SUBSYSTEM=="usb", ATTR{idVendor}=="fafa", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="fafa", MODE="0666", GROUP="plugdev", TAG+="uaccess"

# Ultimarc / PacLed / U-HID - Vendor ID connu : D209
SUBSYSTEM=="usb", ATTR{idVendor}=="d209", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="d209", MODE="0666", GROUP="plugdev", TAG+="uaccess"

# NXP / Freescale KL25Z / Pinscape - Vendor IDs courants : 15A2, 1FC9
SUBSYSTEM=="usb", ATTR{idVendor}=="15a2", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="15a2", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="1fc9", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1fc9", MODE="0666", GROUP="plugdev", TAG+="uaccess"

# Raspberry Pi Pico / RP2040 / Pinscape Pico - Vendor IDs courants : 2E8A, 1209
SUBSYSTEM=="usb", ATTR{idVendor}=="2e8a", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2e8a", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="1209", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1209", MODE="0666", GROUP="plugdev", TAG+="uaccess"

# Arduino Leonardo / Micro / clones - Vendor IDs courants : 2341, 2A03, 1B4F
SUBSYSTEM=="usb", ATTR{idVendor}=="2341", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", MODE="0666", GROUP="dialout", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2341", MODE="0666", GROUP="plugdev", TAG+="uaccess"

SUBSYSTEM=="usb", ATTR{idVendor}=="2a03", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="2a03", MODE="0666", GROUP="dialout", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2a03", MODE="0666", GROUP="plugdev", TAG+="uaccess"

SUBSYSTEM=="usb", ATTR{idVendor}=="1b4f", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1b4f", MODE="0666", GROUP="dialout", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1b4f", MODE="0666", GROUP="plugdev", TAG+="uaccess"

# FTDI USB Serial - Vendor ID : 0403
SUBSYSTEM=="usb", ATTR{idVendor}=="0403", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", MODE="0666", GROUP="dialout", TAG+="uaccess"

# Silicon Labs CP210x - Vendor ID : 10C4
SUBSYSTEM=="usb", ATTR{idVendor}=="10c4", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", MODE="0666", GROUP="dialout", TAG+="uaccess"

# WCH CH340/CH341 - Vendor ID : 1A86
SUBSYSTEM=="usb", ATTR{idVendor}=="1a86", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", MODE="0666", GROUP="dialout", TAG+="uaccess"

# Espressif ESP32 / ESP8266 USB Serial natif - Vendor ID courant : 303A
SUBSYSTEM=="usb", ATTR{idVendor}=="303a", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", MODE="0666", GROUP="dialout", TAG+="uaccess"

# HID générique utile DOF, limité aux devices hidraw
KERNEL=="hidraw*", MODE="0660", GROUP="plugdev", TAG+="uaccess"
EOF2

  chmod 644 "$UDEV"
  udevadm control --reload-rules
  udevadm trigger || true
}

case "$COMPONENT" in
  all)
    install_common
    install_ledwiz
    install_pinscape_kl25z
    install_pinscape_pico
    install_dudes_esp
    install_pacled
    install_ftdi
    install_arduino
    install_serial_usb
    write_udev_rules
    ;;
  base)
    install_common
    write_udev_rules
    ;;
  ledwiz)
    install_common
    install_ledwiz
    write_udev_rules
    ;;
  pinscape-kl25z)
    install_common
    install_pinscape_kl25z
    write_udev_rules
    ;;
  pinscape-pico)
    install_common
    install_pinscape_pico
    write_udev_rules
    ;;
  dudes-esp)
    install_common
    install_dudes_esp
    write_udev_rules
    ;;
  pacled)
    install_common
    install_pacled
    write_udev_rules
    ;;
  ftdi)
    install_common
    install_ftdi
    write_udev_rules
    ;;
  arduino)
    install_common
    install_arduino
    write_udev_rules
    ;;
  serial-usb)
    install_common
    install_serial_usb
    write_udev_rules
    ;;
  *)
    echo "Composant inconnu: $COMPONENT"
    exit 2
    ;;
esac

cat > /opt/pincabos/config/dof/dof-utils-status.json <<EOF2
{
  "last_component": "$COMPONENT",
  "last_run": "$(date '+%F %T')",
  "modified_by": "PinCabOS",
  "function": "DOF Component Install"
}
EOF2

chown -R pinball:pinball /opt/pincabos/config/dof || true

echo
echo "=== Vérification après installation ==="
echo
echo "Groupes pinball:"
id pinball || true

echo
echo "Modules utiles:"
for m in usbhid usbserial cdc_acm ftdi_sio cp210x ch341; do
  if lsmod | awk '{print $1}' | grep -qx "$m"; then
    echo "OK kernel module loaded: $m"
  elif modinfo "$m" >/dev/null 2>&1; then
    echo "OK kernel module available: $m"
  else
    echo "ABSENT kernel module: $m"
  fi
done

echo
echo "UDEV:"
ls -lh "$UDEV" || true

echo
echo "USB:"
lsusb || true

echo
echo "HIDRAW:"
ls -l /dev/hidraw* 2>/dev/null || echo "Aucun hidraw"

echo
echo "SERIAL:"
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || echo "Aucun serial USB"

echo
echo "Installation composant DOF terminée : $COMPONENT"

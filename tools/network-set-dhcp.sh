#!/usr/bin/env bash
# PinCabOs-File created by Karots Sugarpie
set -euo pipefail

echo "=== PinCabOS - DHCP sécurisé avec rollback ==="
echo

IFACE="${1:-}"

if [ -z "$IFACE" ] || [ "$IFACE" = "non détectée" ] || [ "$IFACE" = "non" ] || [ "$IFACE" = "inconnu" ]; then
  echo "Interface non fournie ou invalide, détection automatique..."
  IFACE="$(/opt/pincabos/tools/network-detect-main-iface.sh 2>/dev/null || true)"
fi

if [ -z "${IFACE:-}" ]; then
  echo "ERREUR: aucune carte réseau ethernet physique détectée."
  ip -br link || true
  exit 1
fi

echo "Carte réseau sélectionnée : $IFACE"
echo

OLD_IP="$(ip -4 addr show "$IFACE" 2>/dev/null | awk '/inet / {print $2; exit}' || true)"
OLD_GW="$(ip route 2>/dev/null | awk '/^default / {print $3; exit}' || true)"

echo "État avant changement:"
echo "  IP actuelle      : ${OLD_IP:-aucune}"
echo "  Passerelle       : ${OLD_GW:-aucune}"
echo

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/opt/pincabos/backups/network/safe-dhcp-$STAMP"
mkdir -p "$BACKUP_DIR"

echo "=== Backup Netplan complet ==="
cp -av /etc/netplan/*.yaml "$BACKUP_DIR/" 2>/dev/null || true

restore_backup() {
  echo
  echo "ERREUR: DHCP non validé. Restauration ancienne configuration réseau..."
  echo

  rm -f /etc/netplan/*.yaml 2>/dev/null || true
  cp -av "$BACKUP_DIR"/*.yaml /etc/netplan/ 2>/dev/null || true
  chmod 600 /etc/netplan/*.yaml 2>/dev/null || true

  netplan generate 2>/dev/null || true
  netplan apply 2>/dev/null || true
  systemctl restart systemd-networkd 2>/dev/null || true

  sleep 5

  echo
  echo "État après rollback:"
  ip -br a show "$IFACE" || true
  ip route || true

  echo
  echo "Rollback terminé."
  exit 1
}

echo
echo "=== Écriture Netplan DHCP PinCabOS ==="
cat > /etc/netplan/99-pincabos-network.yaml <<EOF2
# Modifié $(date '+%F %T') par PinCabOS fonction(Network DHCP Safe)
network:
  version: 2
  renderer: networkd
  ethernets:
    ${IFACE}:
      dhcp4: true
      dhcp6: false
      optional: true
EOF2

chmod 600 /etc/netplan/99-pincabos-network.yaml

echo
cat /etc/netplan/99-pincabos-network.yaml
echo

echo "=== Génération Netplan ==="
netplan generate || restore_backup

echo
echo "=== Application Netplan ==="
netplan apply || restore_backup

echo
echo "=== Demande renouvellement DHCP ==="
networkctl renew "$IFACE" 2>/dev/null || true

echo
echo "=== Attente IP DHCP valide ==="
NEW_IP=""
NEW_GW=""

for i in $(seq 1 20); do
  NEW_IP="$(ip -4 addr show "$IFACE" 2>/dev/null | awk '/inet / {print $2; exit}' || true)"
  NEW_GW="$(ip route 2>/dev/null | awk '/^default / {print $3; exit}' || true)"

  if [ -n "$NEW_IP" ] && [ -n "$NEW_GW" ]; then
    break
  fi

  echo "Attente DHCP... $i/20"
  sleep 2
done

if [ -z "$NEW_IP" ] || [ -z "$NEW_GW" ]; then
  restore_backup
fi

echo
echo "=== DHCP validé ==="
echo "Interface : $IFACE"
echo "IP        : $NEW_IP"
echo "Gateway   : $NEW_GW"
echo

echo "=== Résultat réseau ==="
ip -br a show "$IFACE" || true
ip route || true

echo
echo "=== DNS ==="
resolvectl dns "$IFACE" 2>/dev/null || true

echo
echo "=== Adresse WebApp PinCabOS ==="
IPS="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' | grep -v '^127\.' || true)"

if [ -n "$IPS" ]; then
  for ip in $IPS; do
    echo "IMPORTANT - PRENDS CETTE ADRESSE EN NOTE:"
    echo "http://$ip/"
  done
else
  echo "Aucune IP LAN détectée pour l'instant."
fi

echo
echo "DHCP sécurisé terminé."

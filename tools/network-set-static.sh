#!/bin/bash
# PinCabOs-File created by Karots Sugarpie
set -e

IFACE="$1"
IPCIDR="$2"
GATEWAY="$3"
DNS="$4"

if [ -z "$IFACE" ] || [ -z "$IPCIDR" ] || [ -z "$GATEWAY" ]; then
  echo "Usage: $0 INTERFACE IP/CIDR GATEWAY DNS"
  echo "Exemple: $0 ens18 192.168.254.213/24 192.168.254.1 1.1.1.1,8.8.8.8"
  exit 1
fi

if [ -z "$DNS" ]; then
  DNS="1.1.1.1,8.8.8.8"
fi

mkdir -p /etc/netplan /opt/pincabos/backups/network

cp -av /etc/netplan/*.yaml /opt/pincabos/backups/network/ 2>/dev/null || true

cat > /etc/netplan/99-pincabos-network.yaml <<EOF2
# Modifié $(date '+%F %T') par PinCabOS fonction(Network Static)
network:
  version: 2
  renderer: networkd
  ethernets:
    ${IFACE}:
      dhcp4: false
      addresses:
        - ${IPCIDR}
      routes:
        - to: default
          via: ${GATEWAY}
      nameservers:
        addresses: [${DNS}]
EOF2

chmod 600 /etc/netplan/99-pincabos-network.yaml

echo "Nouvelle configuration IP fixe:"
cat /etc/netplan/99-pincabos-network.yaml

echo
echo "Application de la configuration..."
netplan generate
netplan apply

echo
echo "Résultat:"
ip -br a show "$IFACE" || true
ip route | grep default || true

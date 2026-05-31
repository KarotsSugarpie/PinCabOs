#!/usr/bin/env bash
set -euo pipefail

IFACE="$(ip route 2>/dev/null | awk '/^default / {print $5; exit}' || true)"

if [ -z "${IFACE:-}" ] || [ "$IFACE" = "non" ] || [ "$IFACE" = "non détectée" ]; then
  IFACE="$(/opt/pincabos/tools/network-detect-main-iface.sh 2>/dev/null || true)"
fi

if [ -z "${IFACE:-}" ]; then
  echo "interface=non détectée"
  echo "mode=inconnu"
  echo "ipcidr="
  echo "gateway="
  echo "dns="
  exit 0
fi

echo "interface=$IFACE"

MODE="inconnu"

if [ -f /etc/netplan/99-pincabos-network.yaml ]; then
  if grep -A12 -E "^[[:space:]]+$IFACE:" /etc/netplan/99-pincabos-network.yaml | grep -q "dhcp4: true"; then
    MODE="dhcp"
  elif grep -A12 -E "^[[:space:]]+$IFACE:" /etc/netplan/99-pincabos-network.yaml | grep -q "dhcp4: false"; then
    MODE="static"
  fi
fi

if [ "$MODE" = "inconnu" ]; then
  if networkctl status "$IFACE" 2>/dev/null | grep -qi "DHCP4"; then
    MODE="dhcp"
  fi
fi

IPCIDR="$(ip -4 addr show "$IFACE" 2>/dev/null | awk '/inet / {print $2; exit}' || true)"
GW="$(ip route 2>/dev/null | awk '/^default / {print $3; exit}' || true)"
DNS="$(resolvectl dns "$IFACE" 2>/dev/null | sed 's/^.*: //' | tr ' ' ',' || true)"

echo "mode=$MODE"
echo "ipcidr=${IPCIDR:-}"
echo "gateway=${GW:-}"
echo "dns=${DNS:-}"

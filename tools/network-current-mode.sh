#!/usr/bin/env bash
# PinCabOs-File created by Karots Sugarpie
set -u

ORIG="/opt/pincabos/tools/network-current-mode.sh.pincabos-orig"

if [ ! -x "$ORIG" ]; then
  echo "interface="
  echo "mode=inconnu"
  echo "ipcidr="
  echo "gateway="
  echo "dns="
  exit 0
fi

OUT="$("$ORIG" "$@" 2>&1 || true)"

IFACE="$(printf '%s\n' "$OUT" | awk -F= '$1=="interface"{print $2; exit}')"
MODE="$(printf '%s\n' "$OUT" | awk -F= '$1=="mode"{print $2; exit}')"

if [ -z "${IFACE:-}" ]; then
  IFACE="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
fi

if [ "${MODE:-inconnu}" = "inconnu" ] || [ -z "${MODE:-}" ]; then
  if [ -n "${IFACE:-}" ] && ip route show default 2>/dev/null | grep -qE "dev ${IFACE} .*proto dhcp|dev ${IFACE}"; then
    if ip route show default 2>/dev/null | grep -q "proto dhcp"; then
      MODE="dhcp"
    fi
  fi

  if [ "${MODE:-inconnu}" = "inconnu" ] && [ -n "${IFACE:-}" ]; then
    if networkctl status "$IFACE" 2>/dev/null | grep -qiE 'DHCPv4|DHCP'; then
      MODE="dhcp"
    fi
  fi

  if [ "${MODE:-inconnu}" = "inconnu" ] && [ -f /etc/netplan/99-pincabos-network.yaml ]; then
    if grep -qE 'dhcp4:[[:space:]]*false' /etc/netplan/99-pincabos-network.yaml; then
      MODE="static"
    fi
  fi
fi

printf '%s\n' "$OUT" | awk -F= -v mode="$MODE" '
BEGIN { seen=0 }
$1=="mode" {
  print "mode=" mode
  seen=1
  next
}
{ print }
END {
  if (!seen) print "mode=" mode
}
'

#!/bin/bash
# PinCabOs-File created by Karots Sugarpie
set -e

LOG="/opt/pincabos/logs/updates/update-system-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=================================================="
echo " PinCabOs - Update système Ubuntu"
echo " Log: $LOG"
echo "=================================================="

apt update
apt -y upgrade
apt -y autoremove

echo "=================================================="
echo "Update système terminé."
echo "=================================================="

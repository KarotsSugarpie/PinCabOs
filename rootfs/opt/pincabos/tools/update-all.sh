#!/bin/bash
set -e

LOG="/opt/pincabos/logs/updates/update-all-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=================================================="
echo " PinCabOs - Update complet"
echo " Log: $LOG"
echo "=================================================="

/opt/pincabos/tools/update-system.sh
/opt/pincabos/tools/update-vpinfe.sh
/opt/pincabos/tools/update-vpx.sh

echo "=================================================="
echo "Update complet terminé."
echo "=================================================="

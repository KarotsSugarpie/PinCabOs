#!/usr/bin/env bash
clear
echo -e "\033[38;5;208m=== PinCabOS - Rollback WebApp PinCabOS ===\033[0m"

set -e

DST="/opt/pincabos/web"
BACKUP_ROOT="/opt/pincabos/backups"

echo
echo "=== 1) Chercher dernier backup WebApp ==="
LAST_BACKUP="$(ls -1dt "$BACKUP_ROOT"/webapp-before-deploy-* 2>/dev/null | head -1 || true)"

if [ -z "$LAST_BACKUP" ]; then
  echo "ERREUR: aucun backup trouvé dans $BACKUP_ROOT"
  exit 1
fi

echo "Dernier backup trouvé:"
echo "$LAST_BACKUP"

echo
echo "=== 2) Backup de sécurité avant rollback ==="
SAFETY_BACKUP="$BACKUP_ROOT/webapp-before-rollback-$(date +%Y%m%d-%H%M%S)"
sudo cp -a "$DST" "$SAFETY_BACKUP"
echo "Backup sécurité:"
echo "$SAFETY_BACKUP"

echo
echo "=== 3) Restauration ==="
sudo rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$LAST_BACKUP/" "$DST/"

echo
echo "=== 4) Permissions ==="
sudo chown -R pinball:pinball "$DST" || true

echo
echo "=== 5) Redémarrage WebApp ==="
sudo systemctl restart pincabos-web 2>/dev/null || sudo systemctl restart pincabos 2>/dev/null || true
sudo systemctl reload nginx 2>/dev/null || true

echo
echo "=== 6) Statut services ==="
systemctl --no-pager --lines=5 status pincabos-web 2>/dev/null || systemctl --no-pager --lines=5 status pincabos 2>/dev/null || true

echo
echo "=== Rollback terminé ==="

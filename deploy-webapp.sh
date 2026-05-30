#!/usr/bin/env bash
clear
echo -e "\033[38;5;208m=== PinCabOS - Déployer WebApp depuis GitHub export ===\033[0m"

set -e

SRC="/home/pinball/Share/pincabos-github-export/opt/pincabos/web"
DST="/opt/pincabos/web"
BACKUP="/opt/pincabos/backups/webapp-before-deploy-$(date +%Y%m%d-%H%M%S)"

echo
echo "=== 1) Vérifier source ==="
if [ ! -d "$SRC" ]; then
  echo "ERREUR: source absente: $SRC"
  exit 1
fi

echo
echo "=== 2) Backup WebApp actuelle ==="
sudo mkdir -p "$(dirname "$BACKUP")"
sudo cp -a "$DST" "$BACKUP"
echo "Backup: $BACKUP"

echo
echo "=== 3) Déploiement vers /opt/pincabos/web ==="
sudo rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$SRC/" "$DST/"

echo
echo "=== 4) Permissions ==="
sudo chown -R pinball:pinball "$DST" || true

echo
echo "=== 5) Redémarrage WebApp ==="
sudo systemctl restart pincabos-web 2>/dev/null || sudo systemctl restart pincabos 2>/dev/null || true
sudo systemctl reload nginx 2>/dev/null || true

echo
echo "=== 6) Attente socket WebApp ==="
for i in $(seq 1 20); do
  if [ -S /run/pincabos-web/pincabos-web.sock ]; then
    echo "Socket prêt."
    break
  fi
  sleep 0.5
done

echo
echo "=== 7) Test HTTP local ==="
for i in $(seq 1 20); do
  if curl -s -I http://127.0.0.1/ | head -1 | grep -q "200"; then
    echo "WebApp répond OK."
    break
  fi
  sleep 0.5
done

echo
echo "=== 8) Statut services ==="
systemctl --no-pager --lines=8 status pincabos-web 2>/dev/null || systemctl --no-pager --lines=8 status pincabos 2>/dev/null || true

echo
echo "=== Déploiement terminé ==="

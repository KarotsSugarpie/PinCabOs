#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Install Alpha 1.4 full rootfs ===\e[0m"

set -e

if [ ! -d rootfs ]; then
  echo "ERREUR: lance ce script depuis la racine du repo PinCabOS."
  exit 1
fi

echo
echo "=== 1) Copier rootfs ==="
rsync -a rootfs/ /

echo
echo "=== 2) Permissions ==="
chmod +x /opt/pincabos/tools/*.sh 2>/dev/null || true
chmod +x /opt/pincabos/tools/*.py 2>/dev/null || true
chmod +x /opt/pincabos/bin/*.sh 2>/dev/null || true
chmod 440 /etc/sudoers.d/pincabos-webapp 2>/dev/null || true
visudo -cf /etc/sudoers.d/pincabos-webapp 2>/dev/null || true

chown -R pinball:pinball /home/pinball/Tables /home/pinball/.vpinball /home/pinball/Downloads /home/pinball/Exports /home/pinball/Share 2>/dev/null || true

echo
echo "=== 3) Nginx ==="
rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/pincabos-web /etc/nginx/sites-enabled/pincabos-web
nginx -t

echo
echo "=== 4) Services ==="
systemctl daemon-reload
systemctl enable --now pincabos-web.service
systemctl enable pincabos-console.service 2>/dev/null || true
systemctl enable pincabos-screen-layout.service 2>/dev/null || true
systemctl restart nginx

echo
echo "=== OK Alpha 1.4 installé ==="

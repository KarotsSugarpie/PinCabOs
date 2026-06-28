#!/usr/bin/env bash
# PinCabOs-File created by Karots Sugarpie
# PINCABOS_SCRIPT_NAME="pincabos-update-engine-runner.sh"
# PINCABOS_SCRIPT_ROLE="WebApp-triggered update runner for PinCabOS webapp/system modes"
# PINCABOS_SCRIPT_REQUIRES_FILES="/opt/pincabos/scripts/pincabos-update-channel-check.sh /opt/pincabos/install/02-install-engine.sh"
# PINCABOS_SCRIPT_REQUIRES_DIRS="/home/pinball/Tables /home/pinball/.vpinball /opt/pincabos/config/vpinfe /opt/pincabos/logs/updates"


# ---------------------------------------------------------------------------
# PinCabOS update final status guard
# Created by Karots Sugarpie
#
# Requisites:
# - /usr/bin/python3
# - /bin/systemctl
# - /opt/pincabos/logs/updates
#
# Purpose:
# - Prevent WebApp update UI from staying at 90% when the WebApp service
#   is restarted before the final progress JSON is written.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PinCabOS WebApp update completion guard
# Created by Karots Sugarpie
#
# Dependencies/requisites:
# - /usr/bin/python3
# - /bin/systemctl
# - /opt/pincabos/logs/updates
#
# Purpose:
# - Write final 100% progress before restarting pincabos-webapp.
# - Prevent UI from staying blocked at 90% / Redémarrage WebApp.
# ---------------------------------------------------------------------------
pco_update_write_final_100() {
  local status_dir="/opt/pincabos/logs/updates"
  mkdir -p "$status_dir" 2>/dev/null || true

  /usr/bin/python3 - <<'PYSTATUS'
import json
from pathlib import Path
from datetime import datetime

status_dir = Path("/opt/pincabos/logs/updates")
status_dir.mkdir(parents=True, exist_ok=True)

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

payload = {
    "ok": True,
    "done": True,
    "finished": True,
    "running": False,
    "active": False,
    "success": True,
    "percent": 100,
    "progress": 100,
    "stage": "Terminé",
    "step": "Terminé",
    "title": "Terminé",
    "operation": "Terminé",
    "message": "Mise à jour WebApp complétée.",
    "detail": "Redémarrage WebApp lancé en arrière-plan.",
    "updated_at": now,
    "completed_at": now,
}

targets = [
    status_dir / "status.json",
    status_dir / "update-status.json",
    status_dir / "pincabos-update-status.json",
    status_dir / "webapp-status.json",
]

for old in sorted(status_dir.glob("*.json")):
    n = old.name.lower()
    if "status" in n or "update" in n or "webapp" in n:
        targets.append(old)

seen = set()
for target in targets:
    if target in seen:
        continue
    seen.add(target)

    current = {}
    if target.exists():
        try:
            current = json.loads(target.read_text())
            if not isinstance(current, dict):
                current = {}
        except Exception:
            current = {}

    current.update(payload)
    target.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
PYSTATUS

  echo
  echo "=== 4) Terminé ==="
  echo "GO: Mise à jour WebApp complétée"
  echo "GO: Progression finale 100%"
}

pco_update_restart_webapp_background() {
  pco_update_write_final_100

  (
    sleep 2
    /bin/systemctl restart pincabos-webapp 2>/dev/null || true
    /bin/systemctl restart nginx 2>/dev/null || true
  ) >/dev/null 2>&1 &

  echo "GO: Redémarrage WebApp/nginx lancé en arrière-plan"
}

pco_update_force_done_status() {
  local status_dir="/opt/pincabos/logs/updates"
  local now
  now="$(date '+%Y-%m-%d %H:%M:%S')"

  mkdir -p "$status_dir" 2>/dev/null || true

  /usr/bin/python3 - <<'PYSTATUS'
import json
from pathlib import Path
from datetime import datetime

status_dir = Path("/opt/pincabos/logs/updates")
status_dir.mkdir(parents=True, exist_ok=True)

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

payload = {
    "ok": True,
    "done": True,
    "finished": True,
    "running": False,
    "active": False,
    "success": True,
    "percent": 100,
    "progress": 100,
    "stage": "Terminé",
    "step": "Terminé",
    "title": "Terminé",
    "message": "Mise à jour complétée. Redémarrage WebApp en cours.",
    "detail": "La WebApp redémarre en arrière-plan.",
    "updated_at": now,
    "completed_at": now,
}

targets = [
    status_dir / "status.json",
    status_dir / "update-status.json",
    status_dir / "pincabos-update-status.json",
]

for old in sorted(status_dir.glob("*.json")):
    name = old.name.lower()
    if "status" in name or "update" in name:
        targets.append(old)

seen = set()
for target in targets:
    if target in seen:
        continue
    seen.add(target)

    current = {}
    if target.exists():
        try:
            current = json.loads(target.read_text())
            if not isinstance(current, dict):
                current = {}
        except Exception:
            current = {}

    current.update(payload)
    target.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
PYSTATUS
}

pco_update_restart_webapp_async() {
  pco_update_force_done_status

  (
    sleep 2
    /bin/systemctl restart pincabos-webapp 2>/dev/null || true
    /bin/systemctl restart nginx 2>/dev/null || true
  ) >/dev/null 2>&1 &

  echo "GO: statut final 100% écrit; redémarrage WebApp/nginx lancé en arrière-plan"
}

set -Eeuo pipefail

MODE="${1:-}"
case "$MODE" in
  webapp|system) ;;
  *) echo "NOGOOD: mode invalide: $MODE"; exit 2 ;;
esac

LOGDIR="/opt/pincabos/logs/updates"
STATUS="$LOGDIR/pincabos-update-status.json"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/pincabos-update-${MODE}-${TS}.log"
PROTECT="/opt/pincabos/backups/update-protect-${MODE}-${TS}"

mkdir -p "$LOGDIR" "$PROTECT"
exec > >(tee "$LOG") 2>&1

safe_clear() {
  if [ -t 1 ] && [ -n "${TERM:-}" ] && [ "${TERM:-unknown}" != "unknown" ]; then
    clear || true
  fi
}

on_error() {
  local rc="$?"
  echo "NOGOOD: runner update failed rc=$rc"
  write_status "failed" 100 "NOGOOD" "Runner update failed rc=$rc"
  restore_protected || true
  exit "$rc"
}


write_status() {
  local state="$1"
  local pct="$2"
  local step="$3"
  local msg="$4"
  python3 - "$STATUS" "$state" "$pct" "$step" "$msg" "$LOG" <<'PY'
import json, sys, time
p,state,pct,step,msg,log = sys.argv[1:]
data = {
  "ok": True,
  "running": state == "running",
  "state": state,
  "percent": int(pct),
  "step": step,
  "message": msg,
  "events": [step, msg],
  "log": log,
  "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
}
open(p, "w", encoding="utf-8").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY
}

fail() {
  echo "NOGOOD: $*"
  write_status "failed" 100 "NOGOOD" "$*"
  exit 1
}

backup_protected() {
  echo
  echo "=== Backup protections cab ==="
  mkdir -p "$PROTECT/home-pinball-vpinball" "$PROTECT/opt-pincabos-config-vpinfe"

  if [ -f /home/pinball/.vpinball/VPinballX.ini ]; then
    cp -a /home/pinball/.vpinball/VPinballX.ini "$PROTECT/home-pinball-vpinball/VPinballX.ini"
    echo "GO: backup VPinballX.ini"
  fi

  if [ -f /opt/pincabos/config/vpinfe/vpinfe.ini ]; then
    cp -a /opt/pincabos/config/vpinfe/vpinfe.ini "$PROTECT/opt-pincabos-config-vpinfe/vpinfe.ini"
    echo "GO: backup vpinfe.ini"
  fi

  if [ -d /home/pinball/Tables ]; then
    echo "GO: Tables protégées: /home/pinball/Tables"
  else
    echo "SKIP: /home/pinball/Tables absent"
  fi
}

restore_protected() {
  echo
  echo "=== Restore protections cab ==="
  if [ -f "$PROTECT/home-pinball-vpinball/VPinballX.ini" ]; then
    mkdir -p /home/pinball/.vpinball
    cp -a "$PROTECT/home-pinball-vpinball/VPinballX.ini" /home/pinball/.vpinball/VPinballX.ini
    echo "GO: VPinballX.ini restauré"
  fi

  if [ -f "$PROTECT/opt-pincabos-config-vpinfe/vpinfe.ini" ]; then
    mkdir -p /opt/pincabos/config/vpinfe
    cp -a "$PROTECT/opt-pincabos-config-vpinfe/vpinfe.ini" /opt/pincabos/config/vpinfe/vpinfe.ini
    echo "GO: vpinfe.ini restauré"
  fi

  chown -R pinball:pinball /home/pinball/.vpinball /opt/pincabos/config/vpinfe 2>/dev/null || true
}

trap on_error ERR
trap 'restore_protected || true' EXIT

safe_clear
echo "────────────────────────────────────────────────────────────────"
echo " PinCabOS Update Runner - $MODE"
echo "────────────────────────────────────────────────────────────────"

write_status "running" 5 "Départ" "Mode $MODE"

echo
echo "=== 1) Vérifier public install/pkg ==="
write_status "running" 10 "Vérification public" "Téléchargement ins.pincabos.cc/install"
/opt/pincabos/scripts/pincabos-update-channel-check.sh || fail "Vérification public failed"

backup_protected

if [ "$MODE" = "webapp" ]; then
  echo
  echo "=== 2) WebApp update via pkg-pincabos-webapp.zst ==="
  write_status "running" 45 "WebApp" "Application package WebApp dédié"

  WEBAPP_PKG="/opt/pincabos/install/pkg/pkg-pincabos-webapp.zst"
  WEBAPP_STAGE="/tmp/pincabos-webapp-update-${TS}"

  [ -s "$WEBAPP_PKG" ] || fail "Package WebApp absent: $WEBAPP_PKG"

  rm -rf "$WEBAPP_STAGE"
  mkdir -p "$WEBAPP_STAGE"

  echo "Package WebApp: $WEBAPP_PKG"
  zstd -t "$WEBAPP_PKG" || fail "Package WebApp zstd invalide"

  echo
  echo "=== 2A) Extraction WebApp package ==="
  write_status "running" 55 "WebApp" "Extraction package WebApp"
  tar --use-compress-program=unzstd -xf "$WEBAPP_PKG" -C "$WEBAPP_STAGE" || fail "Extraction pkg WebApp failed"

  echo
  echo "=== 2B) Audit contenu WebApp package ==="
  find "$WEBAPP_STAGE" -maxdepth 4 -type f | sed -n '1,120p'

  if [ ! -d "$WEBAPP_STAGE/opt/pincabos/web" ]; then
    fail "Package WebApp invalide: opt/pincabos/web absent"
  fi

  echo
  echo "=== 2C) Backup WebApp actuelle ==="
  WEBAPP_BACKUP="/opt/pincabos/backups/webapp-before-update-${TS}"
  mkdir -p "$WEBAPP_BACKUP"
  if [ -d /opt/pincabos/web ]; then
    rsync -a --delete /opt/pincabos/web/ "$WEBAPP_BACKUP/web/"
    echo "GO: backup WebApp: $WEBAPP_BACKUP/web"
  fi

  echo
  echo "=== 2D) Application WebApp seulement ==="
  write_status "running" 70 "WebApp" "Copie /opt/pincabos/web"
  mkdir -p /opt/pincabos/web
  rsync -a --delete --exclude=".venv/" "$WEBAPP_STAGE/opt/pincabos/web/" /opt/pincabos/web/ || fail "rsync WebApp failed"

  if [ -d "$WEBAPP_STAGE/opt/pincabos/tools" ]; then
    echo "=== 2E) Application outils WebApp inclus ==="
    mkdir -p /opt/pincabos/tools
    rsync -a "$WEBAPP_STAGE/opt/pincabos/tools/" /opt/pincabos/tools/ || fail "rsync tools failed"
  fi

  if [ -d "$WEBAPP_STAGE/opt/pincabos/scripts" ]; then
    echo "=== 2F) Application scripts WebApp inclus ==="
    mkdir -p /opt/pincabos/scripts
    rsync -a "$WEBAPP_STAGE/opt/pincabos/scripts/" /opt/pincabos/scripts/ || fail "rsync scripts failed"
  fi

  echo
  echo "=== 2G) Permissions WebApp ==="
  chown -R pinball:pinball /opt/pincabos/web /opt/pincabos/tools /opt/pincabos/scripts 2>/dev/null || true
  chmod 755 /opt/pincabos/tools/*.sh /opt/pincabos/scripts/*.sh 2>/dev/null || true

  restore_protected
  trap - EXIT

  echo
  echo "=== 3) Validation WebApp ==="
  write_status "running" 90 "Services" "Validation WebApp avant redémarrage"
  python3 -m py_compile /opt/pincabos/web/app.py || fail "app.py syntax failed"
  systemctl daemon-reload || true

  rm -rf "$WEBAPP_STAGE"

  echo
  echo "=== 4) Terminé ==="
  write_status "done" 100 "GO" "Mise à jour WebApp terminée"
  pco_update_write_final_100

  echo "GO: Mise à jour WebApp terminée"
  echo "GO: Progression finale 100%"
  echo "Backup: $WEBAPP_BACKUP"
  echo "Log: $LOG"

  (
    sleep 2
    systemctl restart pincabos-webapp.service 2>/dev/null || systemctl restart pincabos-web.service 2>/dev/null || true
    systemctl restart nginx 2>/dev/null || true
  ) >/dev/null 2>&1 &

  echo "GO: Redémarrage WebApp/nginx lancé en arrière-plan"
  exit 0
fi

echo
echo "=== 2) System update sans DHCP/SSID/reboots intermédiaires ==="
write_status "running" 35 "System" "01-install-system.sh"

export PINCA_UPDATE_MODE="system"
export PINCA_SKIP_DHCP4="1"
export PINCA_SKIP_SSID="1"
export PINCA_NO_INTERMEDIATE_REBOOT="1"
export PINCA_FINAL_REBOOT_ONLY="1"
export PINCA_NO_REBOOT="1"
export PINCA_PROTECT_TABLES="1"
export PINCA_PROTECT_VPX_INI="1"
export PINCA_PROTECT_VPINFE_INI="1"

for script in \
  /opt/pincabos/install/01-install-system.sh \
  /opt/pincabos/install/02-install-engine.sh \
  /opt/pincabos/install/03-install-check.sh
do
  [ -x "$script" ] || chmod +x "$script"
done

/opt/pincabos/install/01-install-system.sh || fail "01-install-system.sh failed"

write_status "running" 60 "System" "02-install-engine.sh --engine"

# This runner is a child of pincabos-webapp.service.
# RUN_02 must defer restarting its parent until final reboot.
export PINCABOS_DETACHED_UPDATE=1
if [ -z "${TERM:-}" ] || [ "${TERM:-}" = "unknown" ]; then
  export TERM=xterm
fi
echo "GO: detached WebApp update mode enabled; WebApp restart deferred to final reboot"

/opt/pincabos/install/02-install-engine.sh --engine || /opt/pincabos/install/02-install-engine.sh || fail "02-install-engine.sh failed"

write_status "running" 82 "System" "03-install-check.sh"
/opt/pincabos/install/03-install-check.sh || fail "03-install-check.sh failed"

restore_protected
trap - EXIT

echo
echo "=== 3) Validation finale ==="
write_status "running" 95 "Validation" "Validation finale avant reboot"
python3 -m py_compile /opt/pincabos/web/app.py || fail "app.py syntax failed"
systemctl daemon-reload || true

write_status "awaiting_reboot" 100 "GO" "System update terminé. Reboot final requis."
echo "GO: System update terminé."
echo "GO: Reboot final autorisé seulement après succès."
echo "Log: $LOG"

# On ne force pas le reboot ici; la page a déjà le bouton/modal reboot.
# Cela évite de couper la WebApp avant que le statut soit écrit.
exit 0

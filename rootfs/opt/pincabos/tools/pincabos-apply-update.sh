#!/usr/bin/env bash
set -euo pipefail

LOCK="/run/pincabos-apply-update.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "ERREUR: une mise à jour PinCabOS est déjà en cours."
  exit 1
fi


if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: pincabos-apply-update.sh [--force] [--dry-run]"
  echo
  echo "  --force    Applique aussi splash/Plymouth/branding si présents dans le package"
  echo "  --dry-run  Vérifie la source sans télécharger/appliquer/rebooter"
  exit 0
fi

FORCE_UPDATE="false"
DRY_RUN="false"

for arg in "$@"; do
  case "$arg" in
    --force|force|--force-update)
      FORCE_UPDATE="true"
      ;;
    --dry-run|dry-run)
      DRY_RUN="true"
      ;;
  esac
done

LOG="/opt/pincabos/logs/updates/pincabos-update-$(date +%Y%m%d-%H%M%S).log"
STATUS="/opt/pincabos/logs/updates/pincabos-update-status.json"
EVENTS="/opt/pincabos/logs/updates/pincabos-update-events.log"

mkdir -p /opt/pincabos/logs/updates /opt/pincabos/updates /opt/pincabos/backups/pincabos-updates

pcos_status() {
  local pct="$1"
  local step="$2"
  local msg="$3"
  local running="${4:-true}"
  local state="${5:-running}"

  python3 - "$STATUS" "$EVENTS" "$LOG" "$pct" "$step" "$msg" "$running" "$state" <<'PY'
import json, sys, pathlib, datetime
status, events, log, pct, step, msg, running, state = sys.argv[1:]
now = datetime.datetime.now().isoformat(timespec="seconds")
events = pathlib.Path(events)
events.parent.mkdir(parents=True, exist_ok=True)
with events.open("a", encoding="utf-8") as f:
    f.write(f"[{now}] {step} - {msg}\n")
try:
    ev = events.read_text(encoding="utf-8").splitlines()[-200:]
except Exception:
    ev = []
data = {
    "ok": True,
    "running": running.lower() == "true",
    "state": state,
    "percent": int(pct),
    "step": step,
    "message": msg,
    "updated_at": now,
    "log": log,
    "events": ev,
}
pathlib.Path(status).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

UPDATE_OK=0
trap 'rc=$?; if [ "$UPDATE_OK" != "1" ] && [ "$rc" -ne 0 ]; then pcos_status 100 "Erreur" "Mise à jour échouée, code $rc" false failed; fi' EXIT

exec > >(tee -a "$LOG") 2>&1

echo -e "\e[38;5;208m=== PinCabOS - Apply update SAFE tar.zst ===\e[0m"
echo "Force update: $FORCE_UPDATE"
echo "Dry run     : $DRY_RUN"
echo "Log         : $LOG"

LATEST_URL="$(python3 - <<'PY'
import json, pathlib
p = pathlib.Path("/opt/pincabos/config/pincabos-update.json")
d = json.loads(p.read_text()) if p.exists() else {}
print(d.get("latest_json_url", "https://update.pincabos.cc/updates/latest.json"))
PY
)"

if [ "$DRY_RUN" = "true" ]; then
  echo "=== DRY RUN PinCabOS update ==="
  echo "Latest URL: $LATEST_URL"
  pcos_status 100 "Dry run" "Vérification dry-run terminée sans appliquer" false done
  UPDATE_OK=1
  exit 0
fi

if [ "$FORCE_UPDATE" = "true" ]; then
  pcos_status 1 "Initialisation" "Préparation force update PinCabOS SAFE" true running
else
  pcos_status 1 "Initialisation" "Préparation update normal PinCabOS SAFE" true running
fi

DOWNLOAD_DIR="/opt/pincabos/updates"
BACKUP_DIR="/opt/pincabos/backups/pincabos-updates"
WORK="/tmp/pincabos-apply-update-$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DOWNLOAD_DIR" "$BACKUP_DIR" "$WORK"

pcos_status 8 "Metadata" "Téléchargement latest.json" true running
curl -fL --connect-timeout 10 --max-time 45 --retry 2 --retry-delay 2 "$LATEST_URL" -o "$WORK/latest.json"
cat "$WORK/latest.json"

URL="$(jq -r '.url' "$WORK/latest.json")"
SHA="$(jq -r '.sha256' "$WORK/latest.json")"
VERSION="$(jq -r '.version' "$WORK/latest.json")"
BUILD="$(jq -r '.build' "$WORK/latest.json")"
REBOOT="$(jq -r '.reboot_required // true' "$WORK/latest.json")"
FORMAT="$(jq -r '.format // empty' "$WORK/latest.json")"

if [ -z "$URL" ] || [ "$URL" = "null" ]; then
  echo "ERREUR: URL update absente dans latest.json"
  exit 1
fi

PKG="$DOWNLOAD_DIR/$(basename "$URL")"

pcos_status 18 "Téléchargement" "Téléchargement package update" true running
curl -fL --connect-timeout 10 --max-time 900 --retry 2 --retry-delay 3 "$URL" -o "$PKG"

pcos_status 30 "SHA256" "Validation intégrité" true running
echo "$SHA  $PKG" | sha256sum -c -

pcos_status 40 "Extraction" "Extraction package" true running
rm -rf "$WORK/extract"
mkdir -p "$WORK/extract"

case "$PKG" in
  *.tar.zst|*.tzst)
    tar --use-compress-program=unzstd -xf "$PKG" -C "$WORK/extract"
    ;;
  *.zip)
    unzip -q "$PKG" -d "$WORK/extract"
    ;;
  *)
    if [ "$FORMAT" = "tar.zst" ]; then
      tar --use-compress-program=unzstd -xf "$PKG" -C "$WORK/extract"
    else
      echo "ERREUR: format package inconnu: $PKG"
      exit 1
    fi
    ;;
esac

[ -d "$WORK/extract/rootfs" ] || { echo "ERREUR: rootfs absent"; exit 1; }

echo "Catalogue utilisé: latest.json"
cat "$WORK/latest.json"

pcos_status 52 "Backup" "Backup local avant update" true running
BK="$BACKUP_DIR/before-${VERSION}-${BUILD}-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK"

for d in /opt/pincabos/web /opt/pincabos/tools /opt/pincabos/config; do
  if [ -d "$d" ]; then
    mkdir -p "$BK$(dirname "$d")"
    cp -a "$d" "$BK$d"
  fi
done

mkdir -p "$BK/etc/systemd/system"
cp -a /etc/systemd/system/pincabos-*.service "$BK/etc/systemd/system/" 2>/dev/null || true

if [ "$FORCE_UPDATE" = "true" ]; then
  for d in /usr/share/plymouth/themes/pincabos /usr/share/backgrounds/pincabos /boot/grub/themes/pincabos; do
    if [ -d "$d" ]; then
      mkdir -p "$BK$(dirname "$d")"
      cp -a "$d" "$BK$d"
    fi
  done
  for f in /etc/plymouth/plymouthd.conf /etc/default/grub.d/pincabos.cfg; do
    if [ -f "$f" ]; then
      mkdir -p "$BK$(dirname "$f")"
      cp -a "$f" "$BK$f"
    fi
  done
fi

echo "Backup: $BK"

ROOT="$WORK/extract/rootfs"

safe_rsync_dir() {
  SRC="$1"
  DST="$2"
  if [ -d "$SRC" ]; then
    mkdir -p "$DST"
    rsync -a "$SRC"/ "$DST"/
  fi
}

safe_copy_file() {
  SRC="$1"
  DST="$2"
  if [ -f "$SRC" ]; then
    mkdir -p "$(dirname "$DST")"
    cp -a "$SRC" "$DST"
  fi
}

pcos_status 64 "Application normale" "Application WebApp/tools/config/services" true running

# SAFE: aucun --delete, aucun rsync vers /
safe_rsync_dir "$ROOT/opt/pincabos/web" "/opt/pincabos/web"
safe_rsync_dir "$ROOT/opt/pincabos/tools" "/opt/pincabos/tools"

# UserBalls PinCabOS: copie safe sans supprimer ni écraser les images utilisateur.
if [ -d "$ROOT/home/pinball/.vpinball/UserBalls" ]; then
  echo "=== UserBalls PinCabOS ==="
  mkdir -p /home/pinball/.vpinball/UserBalls/balls /home/pinball/.vpinball/UserBalls/decals
  rsync -a --ignore-existing "$ROOT/home/pinball/.vpinball/UserBalls/" "/home/pinball/.vpinball/UserBalls/"
  chown -R pinball:pinball /home/pinball/.vpinball/UserBalls 2>/dev/null || true
  chmod -R 775 /home/pinball/.vpinball/UserBalls 2>/dev/null || true
  echo "OK: UserBalls appliqué sans écraser les fichiers existants."
fi


if [ "$FORCE_UPDATE" = "true" ]; then
  pcos_status 68 "Apps PinCabOS" "Application /opt/pincabos/apps depuis le package" true running
  safe_rsync_dir "$ROOT/opt/pincabos/apps" "/opt/pincabos/apps"
fi

mkdir -p /opt/pincabos/config
for f in version.json pincabos-update.json vpx-update.json vpx-engine.json; do
  safe_copy_file "$ROOT/opt/pincabos/config/$f" "/opt/pincabos/config/$f"
done

if [ -d "$ROOT/etc/systemd/system" ]; then
  cp -a "$ROOT"/etc/systemd/system/pincabos-*.service /etc/systemd/system/ 2>/dev/null || true
fi

if [ -d "$ROOT/usr/local/bin" ]; then
  cp -a "$ROOT"/usr/local/bin/pincabos* /usr/local/bin/ 2>/dev/null || true
  cp -a "$ROOT"/usr/local/bin/publish* /usr/local/bin/ 2>/dev/null || true
  cp -a "$ROOT"/usr/local/bin/snap.sh /usr/local/bin/ 2>/dev/null || true
fi

if [ "$FORCE_UPDATE" = "true" ]; then
  pcos_status 72 "Dépendances" "Installation dépendances et migrations latest.json" true running

  if jq -e '.apt_packages and (.apt_packages | length > 0)' "$WORK/latest.json" >/dev/null 2>&1; then
    jq -r '.apt_packages[]' "$WORK/latest.json" > "$WORK/apt-packages.txt"
    apt update || true
    xargs -r apt install -y < "$WORK/apt-packages.txt"
  elif [ -f "$WORK/extract/packages/apt-packages.txt" ]; then
    apt update || true
    xargs -r apt install -y < "$WORK/extract/packages/apt-packages.txt"
  fi

  for s in     "$WORK/extract/scripts/install-deps.sh"     "$WORK/extract/scripts/migrate-alpha1-to-alpha12.sh"
  do
    if [ -x "$s" ]; then
      echo "Run migration: $s"
      bash "$s" || true
    fi
  done

  pcos_status 78 "Force system" "Application composants système/BGFX/branding si présents" true running

  safe_rsync_dir "$ROOT/usr/share/plymouth/themes/pincabos" "/usr/share/plymouth/themes/pincabos"
  safe_rsync_dir "$ROOT/usr/share/backgrounds/pincabos" "/usr/share/backgrounds/pincabos"
  safe_rsync_dir "$ROOT/boot/grub/themes/pincabos" "/boot/grub/themes/pincabos"

  safe_copy_file "$ROOT/etc/plymouth/plymouthd.conf" "/etc/plymouth/plymouthd.conf"
  safe_copy_file "$ROOT/etc/default/grub.d/pincabos.cfg" "/etc/default/grub.d/pincabos.cfg"

  safe_copy_file "$ROOT/opt/pincabos/apps/vpx/current/VPinballX_BGFX" "/opt/pincabos/apps/vpx/current/VPinballX_BGFX"
  safe_copy_file "$ROOT/opt/pincabos/apps/vpx/current/VPinballX_GL" "/opt/pincabos/apps/vpx/current/VPinballX_GL"
  chmod +x /opt/pincabos/apps/vpx/current/VPinballX_* 2>/dev/null || true

  if [ -x "$WORK/extract/scripts/postinstall.sh" ]; then
    echo "Run postinstall"
    bash "$WORK/extract/scripts/postinstall.sh" || true
  fi

  if command -v plymouth-set-default-theme >/dev/null 2>&1 && [ -d /usr/share/plymouth/themes/pincabos ]; then
    plymouth-set-default-theme pincabos || true
  fi

  command -v update-initramfs >/dev/null 2>&1 && update-initramfs -u || true
  command -v update-grub >/dev/null 2>&1 && update-grub || true
fi

pcos_status 88 "Services" "Préparation services PinCabOS" true running

chown -R pinball:pinball /opt/pincabos/web /opt/pincabos/tools /opt/pincabos/config 2>/dev/null || true
chmod +x /opt/pincabos/tools/*.sh 2>/dev/null || true

systemctl daemon-reload

# Si un reboot système est requis, ne pas redémarrer pincabos-web ici.
# Sinon la page Web perd le suivi avant la fin de l'update.
if [ "$REBOOT" = "true" ]; then
  UPDATE_OK=1

  if [ "$FORCE_UPDATE" = "true" ]; then
    REBOOT_LABEL="Force system update terminé"
  else
    REBOOT_LABEL="Update normal terminé"
  fi

  if [ "${PINCABOS_DEFER_REBOOT:-0}" = "1" ]; then
    echo "Reboot requis, mais différé jusqu'à la fin de la mise à jour complète."
    touch /run/pincabos-reboot-required 2>/dev/null || true
    pcos_status 92 "Reboot différé" "$REBOOT_LABEL. Reboot différé jusqu'à la fin du job complet." true running
  else
    pcos_status 100 "Redémarrage requis" "$REBOOT_LABEL. Redémarrage requis. En attente de confirmation dans la WebApp." false awaiting_reboot
    echo "$REBOOT_LABEL. Redémarrage requis. En attente de confirmation dans la WebApp."
  fi
else
  pcos_status 100 "Terminé" "Update terminé sans redémarrage" false done
  UPDATE_OK=1
fi

echo "Update SAFE terminé."

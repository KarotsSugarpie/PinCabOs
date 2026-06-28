#!/usr/bin/env bash
# PinCabOs-File created by Karots Sugarpie
set -Eeuo pipefail

ORANGE='\033[38;5;208m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

MODE="${1:-}"
BASE_URL="https://update.pincabos.cc/updates"

TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="/opt/pincabos/logs"
CACHE_DIR="/tmp/pincabos-update-cache-${MODE}-${TS}"
BACKUP_ROOT="/opt/pincabos/backups"
LOG_FILE="${LOG_DIR}/update-${MODE}-${TS}.log"

mkdir -p "$LOG_DIR" "$CACHE_DIR" "$BACKUP_ROOT"

exec > >(tee -a "$LOG_FILE") 2>&1

echo -e "${ORANGE}=== PinCabOS Update Engine ===${NC}"
echo "Mode : $MODE"
echo "Date : $(date)"
echo "Base : $BASE_URL"
echo "Log  : $LOG_FILE"
echo

if [[ "$MODE" != "webapp" && "$MODE" != "system" ]]; then
  echo -e "${RED}ERREUR: mode invalide. Utilise webapp ou system.${NC}"
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo -e "${RED}ERREUR: lance cette mise à jour en root.${NC}"
  exit 1
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo -e "${RED}ERREUR: commande manquante: $1${NC}"
    exit 1
  }
}

need_cmd curl
need_cmd python3
need_cmd sha256sum
need_cmd cp
need_cmd install

VERSION_JSON="$CACHE_DIR/version.json"
LATEST_JSON="$CACHE_DIR/latest.json"
MANIFEST_JSON="$CACHE_DIR/manifest.json"
PLAN_JSON="$CACHE_DIR/plan.json"
DOWNLOAD_DIR="$CACHE_DIR/downloads"

mkdir -p "$DOWNLOAD_DIR"

echo "=== 1) Télécharger version.json/latest.json/manifest.json ==="
curl -fsSL "$BASE_URL/version.json" -o "$VERSION_JSON"
curl -fsSL "$BASE_URL/latest.json" -o "$LATEST_JSON"

MANIFEST_NAME="$(python3 - "$LATEST_JSON" <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
print(data.get("manifest") or data.get("manifest_json") or "manifest.json")
PY
)"

curl -fsSL "$BASE_URL/${MANIFEST_NAME#/}" -o "$MANIFEST_JSON"

echo "version.json : OK"
echo "latest.json  : OK"
echo "manifest     : $MANIFEST_NAME"
echo

echo "=== 2) Construire plan d'installation filtré ==="

python3 - "$MODE" "$BASE_URL" "$MANIFEST_JSON" "$PLAN_JSON" <<'PY'
import json, sys, os, urllib.parse

mode = sys.argv[1]
base = sys.argv[2].rstrip("/") + "/"
manifest_path = sys.argv[3]
plan_path = sys.argv[4]

with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

files = None

if isinstance(manifest, dict):
    files = (
        manifest.get("files")
        or manifest.get("manifest")
        or manifest.get("entries")
        or manifest.get("payload")
    )
elif isinstance(manifest, list):
    files = manifest

if not isinstance(files, list) or not files:
    raise SystemExit("ERREUR: manifest sans liste files/manifest/entries/payload")

def norm_dest(dest):
    dest = str(dest or "").strip()
    if dest.startswith("rootfs/"):
        dest = "/" + dest[len("rootfs/"):]
    if not dest.startswith("/"):
        dest = "/" + dest.lstrip("/")
    return os.path.normpath(dest)

def is_safe_dest(path):
    if path in ["/", "/.", "/.."]:
        return False
    parts = [p for p in path.split(os.sep) if p]
    return ".." not in parts

def webapp_allowed(path):
    # WebApp volontairement strict.
    # IMPORTANT:
    # - ne pas mettre à jour .venv par HTTP/manifest
    # - ne pas prendre __pycache__, .pyc, backups, caches
    # - ne pas prendre les symlinks nginx sites-enabled/modules-enabled
    allowed_prefixes = (
        "/opt/pincabos/web/",
        "/opt/pincabos/tools/",
        "/etc/systemd/system/pincabos-web.service.d/",
        "/etc/systemd/system/pincabos-webapp.service.d/",
    )

    allowed_exact = {
        "/opt/pincabos/config/version.json",
        "/opt/pincabos/config/pincabos-update.json",
        "/etc/systemd/system/pincabos-web.service",
        "/etc/systemd/system/pincabos-web.service.d",
        "/etc/systemd/system/pincabos-webapp.service",
        "/etc/systemd/system/pincabos-webapp.service.d",
        "/etc/nginx/sites-available/pincabos-web",
    }

    denied_prefixes = (
        "/opt/pincabos/web/.venv/",
        "/opt/pincabos/web/__pycache__/",
        "/opt/pincabos/web/static/__pycache__/",
        "/opt/pincabos/tools/__pycache__/",
        "/etc/nginx/sites-enabled/",
        "/etc/nginx/modules-enabled/",
    )

    denied_contains = (
        "/__pycache__/",
        "/.pytest_cache/",
        "/.mypy_cache/",
        "/.git/",
    )

    denied_suffixes = (
        ".pyc",
        ".pyo",
        ".backup",
        ".bak",
        ".tmp",
        ".swp",
        "~",
    )

    denied_name_fragments = (
        ".backup-",
        ".BROKEN-",
        ".old-",
    )

    if path.startswith(denied_prefixes):
        return False

    if any(x in path for x in denied_contains):
        return False

    if path.endswith(denied_suffixes):
        return False

    if any(x in path for x in denied_name_fragments):
        return False

    if path in allowed_exact:
        return True

    if path.startswith(allowed_prefixes):
        return True

    return False

plan = []
skipped = []

for item in files:
    if isinstance(item, str):
        src = item
        dest = item
        sha256 = None
        mode_file = None
        item_type = "file"
    elif isinstance(item, dict):
        src = item.get("url") or item.get("src") or item.get("path") or item.get("file")
        dest = item.get("dest") or item.get("target") or item.get("path") or item.get("file")
        sha256 = item.get("sha256") or item.get("hash")
        mode_file = item.get("mode")
        item_type = str(item.get("type") or item.get("kind") or "file").lower()
    else:
        continue

    if not src or not dest:
        continue

    clean_dest = norm_dest(dest)

    if not is_safe_dest(clean_dest):
        skipped.append((clean_dest, "destination dangereuse"))
        continue

    if mode == "webapp" and not webapp_allowed(clean_dest):
        skipped.append((clean_dest, "hors filtre webapp"))
        continue

    if item_type in ("symlink", "link", "directory", "dir"):
        skipped.append((clean_dest, f"type ignoré {item_type}"))
        continue

    src = str(src).strip()
    if src.startswith("rootfs/"):
        src = src[len("rootfs/"):]

    if src.startswith("http://") or src.startswith("https://"):
        url = src
    else:
        url = urllib.parse.urljoin(base, src.lstrip("/"))

    plan.append({
        "url": url,
        "dest": clean_dest,
        "sha256": sha256,
        "mode": mode_file,
    })

if not plan:
    raise SystemExit("ERREUR: aucun fichier valide à installer")

with open(plan_path, "w", encoding="utf-8") as f:
    json.dump(plan, f, indent=2, ensure_ascii=False)

print(f"Manifest total      : {len(files)}")
print(f"Plan retenu         : {len(plan)}")
print(f"Entrées ignorées    : {len(skipped)}")
print()

print("Aperçu plan:")
for x in plan[:80]:
    print("  " + x["dest"])
if len(plan) > 80:
    print(f"  ... +{len(plan)-80} autres")

print()
print("Aperçu ignorés:")
for path, reason in skipped[:80]:
    print(f"  SKIP {path} ({reason})")
if len(skipped) > 80:
    print(f"  ... +{len(skipped)-80} autres ignorés")
PY

echo
echo "=== 3) Téléchargement + validation SHA256 ==="

BACKUP_DIR="${BACKUP_ROOT}/update-${MODE}-${TS}"
mkdir -p "$BACKUP_DIR"

python3 - "$PLAN_JSON" "$DOWNLOAD_DIR" "$BACKUP_DIR" <<'PY'
import json, sys, os, subprocess, shutil, pathlib

plan_path = sys.argv[1]
download_dir = sys.argv[2]
backup_dir = sys.argv[3]

with open(plan_path, "r", encoding="utf-8") as f:
    plan = json.load(f)

def run(cmd):
    subprocess.check_call(cmd)

for i, entry in enumerate(plan, 1):
    url = entry["url"]
    dest = entry["dest"]
    sha256 = entry.get("sha256")
    mode = entry.get("mode")

    temp_file = os.path.join(download_dir, f"file-{i}")

    print()
    print(f"[{i}/{len(plan)}] {dest}")
    print(f"URL: {url}")

    try:
        run(["curl", "-fsSL", url, "-o", temp_file])
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"ERREUR téléchargement {url} -> {dest} code={e.returncode}")

    if sha256:
        got = subprocess.check_output(["sha256sum", temp_file], text=True).split()[0]
        if got.lower() != sha256.lower():
            raise SystemExit(f"ERREUR SHA256 pour {dest}: attendu {sha256}, reçu {got}")
        print("SHA256 OK")

    if os.path.exists(dest) and not os.path.islink(dest):
        bdest = os.path.join(backup_dir, dest.lstrip("/"))
        os.makedirs(os.path.dirname(bdest), exist_ok=True)
        shutil.copy2(dest, bdest)
        print(f"Backup: {bdest}")
    elif os.path.islink(dest):
        bdest = os.path.join(backup_dir, dest.lstrip("/") + ".symlink.txt")
        os.makedirs(os.path.dirname(bdest), exist_ok=True)
        pathlib.Path(bdest).write_text(os.readlink(dest), encoding="utf-8")
        print(f"Backup symlink: {bdest}")

    os.makedirs(os.path.dirname(dest), exist_ok=True)

    if os.path.islink(dest):
        os.unlink(dest)

    shutil.copy2(temp_file, dest)

    if mode:
        try:
            os.chmod(dest, int(str(mode), 8))
        except Exception:
            print(f"WARNING: mode invalide ignoré: {mode}")

    print("Installé OK")
PY

echo
echo "=== 4) Post-actions ==="

if [[ "$MODE" == "webapp" ]]; then
  echo "Validation app.py si présent..."
  if [[ -f /opt/pincabos/web/app.py ]]; then
    cd /opt/pincabos/web
    python3 -m py_compile /opt/pincabos/web/app.py
  fi

  echo "Validation nginx..."
  nginx -t

  echo "Reload systemd + restart WebApp..."
  systemctl daemon-reload || true
  systemctl restart pincabos-webapp.service
  systemctl restart pincabos-web.service
  systemctl reload nginx || systemctl restart nginx || true
fi

if [[ "$MODE" == "system" ]]; then
  systemctl daemon-reload || true
fi

echo
echo -e "${GREEN}=== Mise à jour PinCabOS ${MODE} terminée OK ===${NC}"
echo "Backup : $BACKUP_DIR"
echo "Log    : $LOG_FILE"

#!/bin/bash
set -euo pipefail

LOG="/opt/pincabos/logs/updates/update-vpx-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

BASE="/opt/pincabos/apps/vpx"
DL="$BASE/downloads"
CURRENT="$BASE/current"
ENGINE_CFG="/opt/pincabos/config/vpx-engine.json"
UPDATE_CFG="/opt/pincabos/config/vpx-update.json"

mkdir -p "$DL" "$CURRENT" "$BASE/backups" /opt/pincabos/config /opt/pincabos/logs/updates

echo "=================================================="
echo " PinCabOs - Update VPX Linux BGFX"
echo " Log: $LOG"
echo "=================================================="

echo "[1/9] Lire configuration update"
REPO="$(python3 - <<'PY'
import json, pathlib
p=pathlib.Path("/opt/pincabos/config/vpx-update.json")
d=json.loads(p.read_text()) if p.exists() else {}
print(d.get("repo","vpinball/vpinball"))
PY
)"

ASSET_REGEX="$(python3 - <<'PY'
import json, pathlib
p=pathlib.Path("/opt/pincabos/config/vpx-update.json")
d=json.loads(p.read_text()) if p.exists() else {}
print(d.get("asset_regex", r"VPinballX_BGFX.*linux-x64.*Release.*\.zip$"))
PY
)"

FALLBACK_URL="$(python3 - <<'PY'
import json, pathlib
p=pathlib.Path("/opt/pincabos/config/vpx-update.json")
d=json.loads(p.read_text()) if p.exists() else {}
print(d.get("fallback_url",""))
PY
)"

echo "Repo        : $REPO"
echo "Asset regex : $ASSET_REGEX"
echo "Fallback    : $FALLBACK_URL"

echo
echo "[2/9] Backup VPX current"
BK="$BASE/backups/current-before-bgfx-update-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK"

if [ -d "$CURRENT" ] && [ "$(ls -A "$CURRENT" 2>/dev/null)" ]; then
  cp -a "$CURRENT" "$BK/current"
fi

cp -a "$BASE/VPinballX" "$BK/VPinballX-link" 2>/dev/null || true
echo "Backup: $BK"

echo
echo "[3/9] Dépendances"
apt update
apt install -y curl unzip tar gzip file jq

echo
echo "[4/9] Chercher dernière release GitHub publique"
WORK="$DL/vpx-bgfx-update"
rm -rf "$WORK"
mkdir -p "$WORK/zip" "$WORK/extract"

RELEASE_JSON="$WORK/release.json"
API="https://api.github.com/repos/$REPO/releases/latest"

ASSET_URL=""
ASSET_NAME=""

if curl -fsSL "$API" -o "$RELEASE_JSON"; then
  echo "Release détectée:"
  jq -r '.tag_name + " - " + (.name // "")' "$RELEASE_JSON" || true

  ASSET_URL="$(python3 - <<PY
import json, re
d=json.load(open("$RELEASE_JSON"))
rx=re.compile(r'''$ASSET_REGEX''', re.I)
for a in d.get("assets", []):
    name=a.get("name","")
    if rx.search(name):
        print(a.get("browser_download_url",""))
        break
PY
)"

  ASSET_NAME="$(python3 - <<PY
import json, re
d=json.load(open("$RELEASE_JSON"))
rx=re.compile(r'''$ASSET_REGEX''', re.I)
for a in d.get("assets", []):
    name=a.get("name","")
    if rx.search(name):
        print(name)
        break
PY
)"
fi

if [ -z "$ASSET_URL" ]; then
  echo "Aucun asset BGFX linux-x64 trouvé dans latest release publique."
  echo "Utilisation fallback_url."
  ASSET_URL="$FALLBACK_URL"
  ASSET_NAME="$(basename "$FALLBACK_URL")"
fi

if [ -z "$ASSET_URL" ]; then
  echo "ERREUR: aucune source VPX BGFX disponible."
  exit 1
fi

echo "ASSET_NAME=$ASSET_NAME"
echo "ASSET_URL=$ASSET_URL"

echo
echo "[5/9] Download"
cd "$WORK"
curl -L --fail "$ASSET_URL" -o "$ASSET_NAME"
file "$ASSET_NAME"
ls -lh "$ASSET_NAME"

echo
echo "[6/9] Extraction ZIP / archive interne"
unzip -q "$ASSET_NAME" -d "$WORK/zip"

INNER_ARCHIVE="$(find "$WORK/zip" -type f \( -name '*.tar.gz' -o -name '*.tgz' -o -name '*.zip' \) | head -n 1)"

if [ -n "$INNER_ARCHIVE" ]; then
  echo "Archive interne: $INNER_ARCHIVE"
  case "$INNER_ARCHIVE" in
    *.tar.gz|*.tgz)
      tar -xzf "$INNER_ARCHIVE" -C "$WORK/extract"
      ;;
    *.zip)
      unzip -q "$INNER_ARCHIVE" -d "$WORK/extract"
      ;;
  esac
else
  echo "Pas d'archive interne, copie contenu ZIP."
  cp -a "$WORK/zip"/. "$WORK/extract"/
fi

echo
echo "[7/9] Trouver binaire BGFX"
BGFX_BIN="$(find "$WORK/extract" -type f -name 'VPinballX_BGFX' | head -n 1)"

if [ -z "$BGFX_BIN" ]; then
  echo "ERREUR: VPinballX_BGFX introuvable."
  find "$WORK/extract" -maxdepth 5 -type f | sort | head -n 160
  exit 1
fi

echo "BGFX_BIN=$BGFX_BIN"

echo
echo "[8/9] Installer BGFX dans current"
systemctl stop pincabos-frontend.service 2>/dev/null || true

rm -rf "$CURRENT"
mkdir -p "$CURRENT"

SRC_DIR="$(dirname "$BGFX_BIN")"
cp -a "$SRC_DIR"/. "$CURRENT"/

chmod +x "$CURRENT/VPinballX_BGFX"

ln -sfn "$CURRENT/VPinballX_BGFX" "$BASE/VPinballX"

# Compatibilité temporaire avec anciens scripts PinCabOS
ln -sfn "$CURRENT/VPinballX_BGFX" "$CURRENT/VPinballX_GL"

chown -R pinball:pinball "$BASE"
chown -h pinball:pinball "$BASE/VPinballX" "$CURRENT/VPinballX_GL" 2>/dev/null || true

cat > "$ENGINE_CFG" <<EOF2
{
  "engine": "bgfx",
  "binary": "$CURRENT/VPinballX_BGFX",
  "compat_gl_symlink": "$CURRENT/VPinballX_GL",
  "source_url": "$ASSET_URL",
  "asset": "$ASSET_NAME",
  "updated_at": "$(date +%Y%m%d-%H%M%S)",
  "backup": "$BK"
}
EOF2

chown pinball:pinball "$ENGINE_CFG" 2>/dev/null || true

echo
echo "[9/9] Vérifications"
echo "Lien actif:"
readlink -f "$BASE/VPinballX"

echo
echo "Version:"
sudo -u pinball env DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 LD_LIBRARY_PATH="$CURRENT" "$BASE/VPinballX" -v 2>&1 || true

systemctl start pincabos-frontend.service 2>/dev/null || true

echo
echo "=================================================="
echo "Update VPX BGFX terminé."
echo "Backup: $BK"
echo "Source: $ASSET_URL"
echo "=================================================="

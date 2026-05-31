#!/usr/bin/env bash
set -u

echo -e "\033[38;5;208m=== PinCabOS - Mise à jour VPinFE safe ===\033[0m"

TS="$(date +%Y%m%d-%H%M%S)"
APPDIR="/opt/pincabos/apps/frontend"
VPINFE="$APPDIR/vpinfe"
BACKUP="/opt/pincabos/backups/vpinfe/update-$TS"
REPO="https://github.com/superhac/vpinfe.git"

echo
echo "=== Stop VPinFE ==="
systemctl stop pincabos-frontend.service 2>/dev/null || true
# Ne pas faire pkill -f vpinfe ici, car ça tue aussi update-vpinfe.sh lui-même.
# On arrête le service systemd, puis on tue seulement les processus runtime connus.
pkill -f '/opt/pincabos/apps/frontend/vpinfe/.venv/bin/python ./main.py' 2>/dev/null || true
pkill -f '/opt/pincabos/apps/frontend/vpinfe/main.py' 2>/dev/null || true
pkill -f 'chromium.*vpinfe-profile' 2>/dev/null || true

echo
echo "=== Backup avant update ==="
mkdir -p "$BACKUP"

if [ -d "$VPINFE" ]; then
  cp -a "$VPINFE" "$BACKUP/vpinfe-before-update"
fi

if [ -d /home/pinball/.config/vpinfe ]; then
  cp -a /home/pinball/.config/vpinfe "$BACKUP/user-config-vpinfe"
fi

echo
echo "=== Packages système requis ==="
apt update
apt install -y git python3 python3-venv python3-pip python3-dev build-essential

echo
echo "=== Mise à jour source VPinFE ==="
mkdir -p "$APPDIR"

if [ -d "$VPINFE/.git" ]; then
  cd "$VPINFE"
  git fetch --all --prune
  git reset --hard origin/main 2>/dev/null || git reset --hard origin/master
else
  rm -rf "$VPINFE"
  cd "$APPDIR"
  git clone "$REPO" vpinfe
  cd "$VPINFE"
fi

echo
echo "=== Création / réparation venv ==="
cd "$VPINFE"

if [ ! -x ".venv/bin/python" ]; then
  rm -rf .venv
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip setuptools wheel

echo
echo "=== Installation dépendances VPinFE ==="
if [ -f requirements.txt ]; then
  .venv/bin/pip install --upgrade -r requirements.txt
else
  .venv/bin/pip install --upgrade nicegui websockets platformdirs olefile requests aiohttp pillow pyyaml
fi

echo
echo "=== Vérification imports importants ==="
.venv/bin/python - <<'PY'
mods = ["platformdirs", "olefile", "websockets", "requests", "aiohttp", "PIL", "yaml", "nicegui"]
for m in mods:
    __import__(m)
    print("OK", m)
PY

echo
echo "=== Restauration / correction config PinCabOS ==="
mkdir -p /home/pinball/.config/vpinfe

if [ ! -f /home/pinball/.config/vpinfe/vpinfe.ini ] && [ -f "$BACKUP/user-config-vpinfe/vpinfe.ini" ]; then
  cp -a "$BACKUP/user-config-vpinfe/vpinfe.ini" /home/pinball/.config/vpinfe/vpinfe.ini
fi

if [ -f /home/pinball/.config/vpinfe/vpinfe.ini ]; then
  cp -a /home/pinball/.config/vpinfe/vpinfe.ini "/home/pinball/.config/vpinfe/vpinfe.ini.backup-update-$TS"

  python3 <<'PY'
from pathlib import Path

p = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
s = p.read_text(encoding="utf-8")

def set_or_add(section, key, value, text):
    lines = text.splitlines()
    out = []
    in_sec = False
    found_sec = False
    found_key = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_sec and not found_key:
                out.append(f"{key} = {value}")
                found_key = True
            in_sec = stripped.lower() == f"[{section.lower()}]"
            if in_sec:
                found_sec = True
            out.append(line)
            continue

        if in_sec and (stripped.lower().startswith(key.lower() + " ") or stripped.lower().startswith(key.lower() + "=")):
            out.append(f"{key} = {value}")
            found_key = True
        else:
            out.append(line)

    if in_sec and not found_key:
        out.append(f"{key} = {value}")

    if not found_sec:
        out.append("")
        out.append(f"[{section}]")
        out.append(f"{key} = {value}")

    return "\n".join(out) + "\n"

s = set_or_add("Settings", "vpxbinpath", "/opt/pincabos/apps/vpx/scripts/run-vpx.sh", s)
s = set_or_add("Settings", "tablerootdir", "/home/pinball/Tables", s)
s = set_or_add("Settings", "vpxinipath", "/home/pinball/.local/share/VPinballX/10.8/VPinballX.ini", s)
s = set_or_add("Settings", "autoupdatemediaonstartup", "false", s)
s = set_or_add("Network", "themeassetsport", "8000", s)
s = set_or_add("Network", "manageruiport", "8001", s)

p.write_text(s, encoding="utf-8")
PY
else
  cat > /home/pinball/.config/vpinfe/vpinfe.ini <<'INI'
[Displays]
tablescreenid = 0
tableorientation = landscape
tablerotation = 0
dmdscreenid = 0
cabmode = false

[Settings]
vpxbinpath = /opt/pincabos/apps/vpx/scripts/run-vpx.sh
tablerootdir = /home/pinball/Tables
vpxinipath = /home/pinball/.local/share/VPinballX/10.8/VPinballX.ini
theme = Trinidad
autoupdatemediaonstartup = false
splashscreen = false
chromeoptions = --no-sandbox --disable-dev-shm-usage --disable-gpu --no-first-run --disable-software-rasterizer --disable-features=UseOzonePlatform --user-data-dir=/home/pinball/snap/chromium/common/vpinfe-profile
disabledefaultchromeoptions = false

[Logger]
level = debug
console = true

[Network]
themeassetsport = 8000
manageruiport = 8001
INI
fi

echo
echo "=== Réécriture run-vpinfe.sh avec venv obligatoire ==="
cat > /opt/pincabos/tools/run-vpinfe.sh <<'RUNEOF'
#!/usr/bin/env bash
set -u

APP="/opt/pincabos/apps/frontend/vpinfe"
PY="$APP/.venv/bin/python"

export HOME=/home/pinball
export USER=pinball
export LOGNAME=pinball
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="/run/user/$(id -u pinball)"
export XAUTHORITY="/home/pinball/.Xauthority"
export PYTHONUNBUFFERED=1

if [ ! -x "$PY" ]; then
  echo "ERREUR: venv Python introuvable: $PY"
  exit 1
fi

if [ ! -f "$APP/main.py" ]; then
  echo "ERREUR: main.py introuvable dans $APP"
  exit 1
fi

cd "$APP" || exit 1

if [ "$(id -u)" = "0" ]; then
  exec runuser -u pinball -- env \
    HOME="$HOME" \
    USER="$USER" \
    LOGNAME="$LOGNAME" \
    DISPLAY="$DISPLAY" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    XAUTHORITY="$XAUTHORITY" \
    PYTHONUNBUFFERED=1 \
    "$PY" ./main.py
else
  exec "$PY" ./main.py
fi
RUNEOF

chmod +x /opt/pincabos/tools/run-vpinfe.sh

echo
echo "=== Service systemd VPinFE ==="
cat > /etc/systemd/system/pincabos-frontend.service <<'SERVICEEOF'
[Unit]
Description=PinCabOs Frontend - VPinFE
After=network-online.target lightdm.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/pincabos/apps/frontend/vpinfe
ExecStart=/opt/pincabos/tools/run-vpinfe.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICEEOF

echo
echo "=== Permissions ==="
chown -R pinball:pinball /opt/pincabos/apps/frontend/vpinfe
chown -R pinball:pinball /home/pinball/.config/vpinfe
chown -R pinball:pinball /home/pinball 2>/dev/null || true

echo
echo "=== Redémarrage VPinFE ==="
systemctl daemon-reload
systemctl reset-failed pincabos-frontend.service
systemctl enable pincabos-frontend.service
systemctl restart pincabos-frontend.service

sleep 10

echo

echo
echo "=== Vérification Chromium VPinFE bundlé ==="
CHROME="/opt/pincabos/apps/frontend/vpinfe/chromium/linux/chrome/chrome"

if [ ! -x "$CHROME" ]; then
  echo "ERREUR: Chromium VPinFE absent ou non exécutable: $CHROME"
  echo "VPinFE risque de redémarrer en boucle."
  echo "Restaure le dossier chromium depuis un backup VPinFE ou utilise le build VPinFE avec Chromium bundlé."
  exit 1
fi

"$CHROME" --version || true

echo "=== Status VPinFE ==="
systemctl status pincabos-frontend.service --no-pager --full || true

echo
echo "=== Logs VPinFE ==="
journalctl -u pincabos-frontend.service -b --no-pager | tail -n 160

echo
echo "=== Backup update ==="
echo "$BACKUP"

echo
echo "=== Fin update VPinFE safe ==="

echo
echo "=== PinCabOS force VPinFE app_version after update ==="

PIN_VERSION_TAG=""

# 1) Essayer de lire le tag exact depuis git, si le dossier est encore un repo git.
PIN_VERSION_TAG="$(git describe --tags --abbrev=0 2>/dev/null || true)"

# 2) Sinon, prendre la dernière release officielle GitHub.
if [ -z "$PIN_VERSION_TAG" ]; then
  PIN_VERSION_TAG="$(python3 - <<'PYTAG'
import json
import urllib.request

try:
    with urllib.request.urlopen("https://api.github.com/repos/superhac/vpinfe/releases/latest", timeout=15) as r:
        data = json.load(r)
    print((data.get("tag_name") or "").strip())
except Exception:
    print("")
PYTAG
)"
fi

# 3) Si rien ne marche, ne pas écrire une fausse version fixe.
if [ -z "$PIN_VERSION_TAG" ]; then
  echo "WARN: impossible de détecter la version VPinFE. app_version.py non modifié."
else
  cat > "$VPINFE/common/app_version.py" <<EOFVERSION
"""Build/version metadata for VPinFE."""

APP_VERSION = "$PIN_VERSION_TAG"


def get_version() -> str:
    return APP_VERSION
EOFVERSION

  find "$VPINFE" -path "*/__pycache__/app_version*.pyc" -type f -delete 2>/dev/null || true
  chown pinball:pinball "$VPINFE/common/app_version.py" 2>/dev/null || true
  echo "VPinFE app_version.py forcé à: $PIN_VERSION_TAG"
fi


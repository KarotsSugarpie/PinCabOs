#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - DOF Import depuis Downloads ===\e[0m"

set -e

DL="/home/pinball/Downloads"
VPX_RUNTIME="/opt/pincabos/apps/vpx/current/extracted"

DOF_MAIN="/opt/pincabos/config/dof"
DOF_PREF="/home/pinball/.vpinball/DirectOutput"
DOF_HOME="/home/pinball/DirectOutput"
DOF_RUNTIME="$VPX_RUNTIME/DirectOutput"
DOF_RUNTIME_CONFIG="$VPX_RUNTIME/config"

MANIFEST="/opt/pinball/essentiels/pincabos-manifest"
TS="$(date +%Y%m%d-%H%M%S)"
WORK="/tmp/pincabos-dofimport-$TS"
LOG="/home/pinball/Share/dofimport-$TS.txt"

mkdir -p "$WORK" "$DOF_MAIN" "$DOF_PREF" "$DOF_HOME" "$DOF_RUNTIME" "$DOF_RUNTIME_CONFIG" \
  "$MANIFEST/config/dof" "$MANIFEST/backups/dof" /home/pinball/Share

{
echo "=== PinCabOS - dofimport.sh ==="
date
echo
echo "Source Downloads : $DL"
echo "DOF principal    : $DOF_MAIN"
echo "VPX prefpath     : $DOF_PREF"
echo "VPX runtime DOF  : $DOF_RUNTIME"
echo "VPX runtime conf : $DOF_RUNTIME_CONFIG"

echo
echo "=== 1) Chercher directoutputconfig*.zip dans Downloads ==="
find "$DL" -maxdepth 1 -type f \( \
  -iname 'directoutputconfig*.zip' -o \
  -iname '*directoutput*.zip' -o \
  -iname '*dof*.zip' \
\) | sort | tee /tmp/pincabos-dof-zips.txt

if [ ! -s /tmp/pincabos-dof-zips.txt ]; then
  echo
  echo "ERREUR: aucun ZIP DOF trouvé dans $DL"
  echo
  echo "Nom attendu exemple:"
  echo "  directoutputconfig*.zip"
  echo
  echo "Fichiers présents:"
  ls -lah "$DL"
  exit 1
fi

echo
echo "=== 2) Backup ancienne config DOF ==="
tar -czf "$MANIFEST/backups/dof/dof-before-dofimport-$TS.tar.gz" \
  -C / \
  opt/pincabos/config/dof \
  home/pinball/.vpinball/DirectOutput \
  home/pinball/DirectOutput \
  opt/pincabos/apps/vpx/current/extracted/DirectOutput \
  opt/pincabos/apps/vpx/current/extracted/config \
  2>/dev/null || true

echo
echo "=== 3) Extraire ZIP DOF ==="
while read -r ZIP; do
  echo
  echo "Archive:"
  echo "$ZIP"
  unzip -o "$ZIP" -d "$WORK"
done < /tmp/pincabos-dof-zips.txt

echo
echo "=== 4) Fichiers extraits ==="
find "$WORK" -type f | sort | sed -n '1,200p'

echo
echo "=== 5) Sélection fichiers DOF utiles ==="
find "$WORK" -type f \( \
  -iname 'directoutputconfig*.ini' -o \
  -iname 'GlobalConfig_B2SServer.xml' -o \
  -iname 'GlobalConfig*.xml' -o \
  -iname 'cabinet.xml' -o \
  -iname '*cabinet*.xml' \
\) | sort | tee /tmp/pincabos-dof-useful.txt

if [ ! -s /tmp/pincabos-dof-useful.txt ]; then
  echo
  echo "ERREUR: aucun fichier utile trouvé."
  echo "Recherche attendue:"
  echo "  directoutputconfig*.ini"
  echo "  GlobalConfig*.xml"
  echo "  cabinet*.xml"
  exit 1
fi

echo
echo "=== 6) Installer dans /opt/pincabos/config/dof ==="
while read -r F; do
  echo "Install: $F"
  cp -av "$F" "$DOF_MAIN/"
done < /tmp/pincabos-dof-useful.txt

chmod 644 "$DOF_MAIN"/* 2>/dev/null || true

echo
echo "=== 7) Répliquer aux chemins DOF/VPX ==="
rsync -a --delete "$DOF_MAIN"/ "$DOF_PREF"/
rsync -a --delete "$DOF_MAIN"/ "$DOF_HOME"/
rsync -a --delete "$DOF_MAIN"/ "$DOF_RUNTIME"/
rsync -a --delete "$DOF_MAIN"/ "$DOF_RUNTIME_CONFIG"/

chown -R pinball:pinball "$DOF_PREF" "$DOF_HOME" /home/pinball/.vpinball
chmod 755 "$DOF_RUNTIME" "$DOF_RUNTIME_CONFIG" 2>/dev/null || true
chmod 644 "$DOF_RUNTIME"/* "$DOF_RUNTIME_CONFIG"/* 2>/dev/null || true

echo
echo "=== 8) Sauver dans manifest ==="
rsync -a --delete "$DOF_MAIN"/ "$MANIFEST/config/dof/"

echo
echo "=== 9) Vérification fichiers DOF ==="
echo "--- $DOF_MAIN ---"
ls -lah "$DOF_MAIN"

echo
echo "--- $DOF_PREF ---"
ls -lah "$DOF_PREF"

echo
echo "--- $DOF_RUNTIME ---"
ls -lah "$DOF_RUNTIME"

echo
echo "--- $DOF_RUNTIME_CONFIG ---"
ls -lah "$DOF_RUNTIME_CONFIG"

echo
echo "=== 10) Vérifier devices/cabinet dans config ==="
grep -RinE 'Ultimate VPinball|LedWiz|LED-Wiz|DudesCab|fafa|2e8a|DirectOutput' \
  "$DOF_MAIN" "$DOF_PREF" "$DOF_RUNTIME" "$DOF_RUNTIME_CONFIG" || true

echo
echo "=== 11) Vérifier activation VPX ==="
grep -nE 'B2SPlugins|DOFPlugin|B2SWindows' /home/pinball/.vpinball/VPinballX.ini || true

echo
echo "=== 12) USB toys ==="
lsusb | grep -Ei 'fafa|2e8a|led|dudes' || lsusb

echo
echo "=== Services systemd ==="
if systemctl --failed --no-pager --quiet; then
  echo "OK: aucun service failed."
else
  systemctl --failed --no-pager
fi

echo
echo "=== OK ==="
echo "DOF importé depuis Downloads."

} 2>&1 | tee "$LOG"

chown pinball:pinball "$LOG" 2>/dev/null || true

echo
echo "Log:"
echo "$LOG"

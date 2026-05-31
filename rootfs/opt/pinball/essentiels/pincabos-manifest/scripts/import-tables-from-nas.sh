#!/bin/bash
clear
echo -e "\e[38;5;208m=== PinCabOS - Import tables NAS vers /home/pinball/Tables ===\e[0m"

set -e

NAS_TABLES="/mnt/pincabos-nas/PinCabOs/tables"
DEST="/home/pinball/Tables"
LOG="/home/pinball/Share/import-tables-nas-$(date +%Y%m%d-%H%M%S).txt"

mkdir -p "$DEST" /home/pinball/Share

{
echo "=== PinCabOS import tables depuis NAS ==="
date
echo
echo "Source : $NAS_TABLES"
echo "Dest   : $DEST"

echo
echo "=== 1) Vérifier NAS ==="
if ! mount | grep -q "/mnt/pincabos-nas"; then
  echo "ERREUR: NAS non monté sur /mnt/pincabos-nas"
  exit 1
fi

if [ ! -d "$NAS_TABLES" ]; then
  echo "ERREUR: dossier tables absent sur NAS: $NAS_TABLES"
  echo
  echo "Contenu PinCabOs NAS:"
  ls -lah /mnt/pincabos-nas/PinCabOs || true
  exit 1
fi

echo
echo "=== 2) Fichiers disponibles dans NAS tables ==="
find "$NAS_TABLES" -maxdepth 2 -type f | sort

echo
echo "=== 3) Chercher archive pincabos/tables ==="
ARCHIVE="$(find "$NAS_TABLES" -maxdepth 2 -type f \( \
  -iname '*.zip' -o \
  -iname '*.tar.gz' -o \
  -iname '*.tgz' -o \
  -iname '*.tar.xz' -o \
  -iname '*.tar.zst' -o \
  -iname '*.7z' \
\) | sort | head -n 1)"

if [ -z "$ARCHIVE" ]; then
  echo
  echo "Aucune archive trouvée. On va synchroniser le dossier tel quel."
  echo
  rsync -aH --info=progress2 "$NAS_TABLES"/ "$DEST"/
else
  echo
  echo "Archive trouvée:"
  echo "$ARCHIVE"

  echo
  echo "=== 4) Backup index avant extraction ==="
  find "$DEST" -maxdepth 3 -type f | sort > "/home/pinball/Share/tables-before-$TS.txt" || true

  echo
  echo "=== 5) Extraire en gardant arborescence intacte ==="
  case "$ARCHIVE" in
    *.zip|*.ZIP)
      unzip -o "$ARCHIVE" -d "$DEST"
      ;;
    *.tar.gz|*.tgz)
      tar -xzf "$ARCHIVE" -C "$DEST"
      ;;
    *.tar.xz)
      tar -xJf "$ARCHIVE" -C "$DEST"
      ;;
    *.tar.zst)
      tar --zstd -xf "$ARCHIVE" -C "$DEST"
      ;;
    *.7z)
      7z x "$ARCHIVE" -o"$DEST" -y
      ;;
    *)
      echo "ERREUR: format archive non supporté: $ARCHIVE"
      exit 1
      ;;
  esac
fi

echo
echo "=== 6) Permissions pinball ==="
chown -R pinball:pinball "$DEST"

echo
echo "=== 7) Résumé tables VPX trouvées ==="
find "$DEST" -type f -iname '*.vpx' | sort | tee /home/pinball/Share/tables-vpx-found.txt

COUNT="$(find "$DEST" -type f -iname '*.vpx' | wc -l)"
echo
echo "Nombre de tables .vpx trouvées: $COUNT"

echo
echo "=== 8) Arborescence top-level ==="
find "$DEST" -maxdepth 2 -type d | sort

echo
echo "=== OK import tables ==="

} 2>&1 | tee "$LOG"

chown pinball:pinball "$LOG" /home/pinball/Share/tables-vpx-found.txt 2>/dev/null || true

echo
echo "Log:"
echo "$LOG"

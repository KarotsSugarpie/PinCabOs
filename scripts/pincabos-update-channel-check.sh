#!/usr/bin/env bash
# PinCabOs-File created by Karots Sugarpie
# PINCABOS_SCRIPT_NAME="pincabos-update-channel-check.sh"
# PINCABOS_SCRIPT_ROLE="Refresh public install tree from ins.pincabos.cc/install and validate pkg-pincabos-web.zst"
# PINCABOS_SCRIPT_REQUIRES_COMMANDS="/usr/bin/curl /usr/bin/wget /usr/bin/sha256sum /usr/bin/python3 /usr/bin/tar /usr/bin/zstd"
# PINCABOS_SCRIPT_REQUIRES_DIRS="/opt/pincabos/install /opt/pincabos/download /opt/pincabos/logs/updates"
set -Eeuo pipefail

safe_clear() {
  if [ -t 1 ] && [ -n "${TERM:-}" ] && [ "${TERM:-unknown}" != "unknown" ]; then
    clear || true
  fi
}

pco_fetch_public() {
  local rel="$1"
  local dst="$2"
  local base="${PCO_PUBLIC_INSTALL_BASE:-${INSTALL_BASE:-${BASE_URL:-https://ins.pincabos.cc/install}}}"
  local url="${base%/}/${rel#/}"
  local rc=1

  mkdir -p "$(dirname "$dst")"

  # Retry principal.
  if curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 "$url" -o "$dst.tmp"; then
    mv -f "$dst.tmp" "$dst"
    return 0
  fi

  rm -f "$dst.tmp"

  # Fallback explicite pour fichiers pkg, utile pendant transition nginx/cache.
  if [[ "$rel" == pkg/* ]]; then
    local fallback="https://ins.pincabos.cc/install/${rel#/}"
    if [ "$fallback" != "$url" ]; then
      if curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 180 "$fallback" -o "$dst.tmp"; then
        mv -f "$dst.tmp" "$dst"
        return 0
      fi
      rm -f "$dst.tmp"
    fi
  fi

  echo "NOGOOD: download failed: $url"
  return 1
}


PCO_PUBLIC_INSTALL_BASE="${PCO_PUBLIC_INSTALL_BASE:-https://ins.pincabos.cc/install}"


safe_clear
echo "────────────────────────────────────────────────────────────────"
echo " PinCabOS Update - Vérifier public ins.pincabos.cc/install"
echo "────────────────────────────────────────────────────────────────"

BASE="${PINCA_INSTALL_BASE_URL:-https://ins.pincabos.cc/install}"
DEST="/opt/pincabos/install"
PKGDIR="$DEST/pkg"
LOGDIR="/opt/pincabos/logs/updates"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/channel-check-${TS}.log"

mkdir -p "$DEST" "$PKGDIR" "$LOGDIR" /opt/pincabos/download
exec > >(tee "$LOG") 2>&1

go() { echo "GO: $*"; }
nogood() { echo "NOGOOD: $*"; exit 1; }

echo
echo "=== Source ==="
echo "$BASE"

echo
echo "=== 1) Outils requis ==="
for c in curl wget sha256sum python3 tar zstd; do
  command -v "$c" >/dev/null 2>&1 || nogood "commande manquante: $c"
  go "$c"
done

echo
echo "=== 2) Téléchargement fichiers publics connus ==="

download_one() {
  local rel="$1"
  local dst="$DEST/$rel"
  mkdir -p "$(dirname "$dst")"
  if curl -fsSL --connect-timeout 10 --retry 2 "$BASE/$rel" -o "$dst.tmp"; then
    mv -f "$dst.tmp" "$dst"
    case "$dst" in
      *.sh) chmod 0755 "$dst" ;;
      *) chmod 0644 "$dst" ;;
    esac
    go "$rel"
  else
    rm -f "$dst.tmp"
    return 1
  fi
}

required=(
  "go-pincabos.sh"
  "help-pincabos.sh"
  "01-install-system.sh"
  "02-install-engine.sh"
  "03-install-check.sh"
  "install.json"
  "pkg/latest.json"
  "pkg/pkg-pincabos-web.zst"
  "pkg/pkg-pincabos-web.sha256"
  "pkg/pkg-pincabos-web.manifest.json"
)

optional=(
  "PCOSInstallWP.png"
  "pkg/checksums.sha256"
  "pkg/manifest.txt"
  "pkg/pkg-pincabos-webapp.zst"
  "packages/pkg-lib.sh"
  "packages/pkg-apt-base.sh"
  "packages/pkg-monitoring.sh"
  "packages/pkg-python.sh"
  "packages/pkg-nginx.sh"
  "packages/pkg-x11.sh"
  "packages/pkg-lightdm.sh"
  "packages/pkg-openbox.sh"
  "packages/pkg-chrome.sh"
  "packages/pkg-plymouth.sh"
  "packages/pkg-vpx-bgfx-runtime.sh"
  "packages/pkg-vpinfe-runtime.sh"
  "packages/pkg-libdof-runtime.sh"
  "packages/pkg-system-validation.sh"
  "modules/modules.json"
  "modules/system/mod-splash.sh"
  "modules/network/mod-dhcp4.sh"
  "modules/network/mod-ssid.sh"
)

fail=0
for rel in "${required[@]}"; do
  download_one "$rel" || { echo "NOGOOD: requis absent: $rel"; fail=$((fail+1)); }
done

for rel in "${optional[@]}"; do
  download_one "$rel" || echo "SKIP: optionnel absent: $rel"
done

[ "$fail" -eq 0 ] || nogood "fichiers requis manquants: $fail"

echo
echo "=== 3) Permissions / symlinks ==="
find "$DEST" -type f -name "*.sh" -exec chmod 0755 {} \; 2>/dev/null || true
ln -sfn "$DEST/go-pincabos.sh" /usr/local/bin/go-pincabos 2>/dev/null || true
ln -sfn "$DEST/help-pincabos.sh" /usr/local/bin/help-pincabos 2>/dev/null || true
chown -R pinball:pinball "$DEST" 2>/dev/null || true
go "permissions/symlinks"

echo
echo "=== 4) Validation syntaxe scripts critiques ==="
for f in "$DEST/go-pincabos.sh" "$DEST/01-install-system.sh" "$DEST/02-install-engine.sh" "$DEST/03-install-check.sh"; do
  bash -n "$f" || nogood "syntaxe cassée: $f"
  go "syntax OK: $f"
done

echo
echo "=== 5) Validation SHA pkg-pincabos-web.zst ==="
cd "$PKGDIR"
expected="$(awk '{print $1}' pkg-pincabos-web.sha256 | head -1)"
actual="$(sha256sum pkg-pincabos-web.zst | awk '{print $1}')"

echo "expected=$expected"
echo "actual  =$actual"

[ -n "$expected" ] || nogood "SHA expected vide"
[ "$expected" = "$actual" ] || nogood "SHA mismatch pkg-pincabos-web.zst"
go "SHA pkg-pincabos-web.zst"

echo
echo "=== 6) Validation latest.json ==="
python3 -m json.tool "$PKGDIR/latest.json" >/dev/null
grep -q "pkg-pincabos-web.zst" "$PKGDIR/latest.json" || nogood "latest.json ne référence pas pkg-pincabos-web.zst"
go "latest.json"

echo
echo "=== Résumé ==="
du -sh "$DEST" "$PKGDIR" 2>/dev/null || true
echo "GO: Update channel public install/pkg prêt"
echo "Log: $LOG"

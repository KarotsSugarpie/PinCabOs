#!/bin/bash
export DISPLAY="${DISPLAY:-:0}"

# VPX Linux / NVIDIA / X11
export __GL_SYNC_TO_VBLANK=1
export __GL_YIELD="USLEEP"

VPX="/opt/pincabos/apps/vpx/VPinballX"

if [ ! -x "$VPX" ]; then
  echo "ERREUR: VPX absent ou non exécutable: $VPX"
  exit 1
fi

exec "$VPX" "$@"

#!/bin/bash
# Lancé par LightDM pendant le setup display.
# Ne doit jamais bloquer LightDM si erreur.

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/var/run/lightdm/root/:0}"

/opt/pincabos/bin/pincabos-apply-boot-screen-layout.sh \
  >/home/pinball/Share/pincabos-lightdm-display-setup.log 2>&1 || true

exit 0

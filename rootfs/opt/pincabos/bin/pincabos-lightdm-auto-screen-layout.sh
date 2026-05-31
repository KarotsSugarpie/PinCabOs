#!/bin/bash
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/var/run/lightdm/root/:0}"

/opt/pincabos/bin/autoscreen.sh \
  >/home/pinball/Share/pincabos-lightdm-autoscreen.log 2>&1 || true

exit 0

#!/bin/bash
export DISPLAY="${DISPLAY:-:0}"

# PinCabOS VPinFE wrapper
cd "/opt/pincabos/apps/frontend/vpinfe/current/vpinfe"
exec "/opt/pincabos/apps/frontend/vpinfe/current/vpinfe/vpinfe" "$@"

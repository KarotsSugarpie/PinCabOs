#!/bin/bash
export DISPLAY="${DISPLAY:-:0}"

google-chrome \
  --no-first-run \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --start-fullscreen \
  --kiosk \
  "http://localhost/"

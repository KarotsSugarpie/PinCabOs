#!/usr/bin/env bash
# PinCabOs-File created by Karots Sugarpie
set +e

MODE="${1:-webapp}"

if [ "$MODE" != "webapp" ] && [ "$MODE" != "system" ]; then
  echo "Mode invalide: $MODE"
  exit 2
fi

if [ "$MODE" = "system" ]; then
  TITLE="Mise à jour PinCabOS System"
  SCRIPT="/opt/pincabos/tools/update-system.sh"
else
  TITLE="Mise à jour PinCabOS WebApp"
  SCRIPT="/opt/pincabos/tools/update-webapp.sh"
fi

TS="$(date +%Y%m%d-%H%M%S)"
STATUS_DIR="/opt/pincabos/logs/updates"
STATUS="$STATUS_DIR/pincabos-update-status.json"
LOG="/opt/pincabos/logs/update-${MODE}-${TS}.log"

mkdir -p "$STATUS_DIR" /opt/pincabos/logs

python3 - "$STATUS" "$MODE" "$TITLE" "$LOG" <<'PY'
import json, sys, datetime, pathlib

status_path = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
title = sys.argv[3]
log = sys.argv[4]
now = datetime.datetime.now().isoformat(timespec="seconds")

status = {
    "running": True,
    "done": False,
    "ok": False,
    "mode": mode,
    "title": title,
    "message": title + " lancée...",
    "started_at": now,
    "finished_at": None,
    "log": log,
    "events": [
        f"[{now}] {title} lancée",
        f"[{now}] Log: {log}",
    ],
}

status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
PY

echo "=== $TITLE ===" >> "$LOG"
date >> "$LOG"
echo "Mode: $MODE" >> "$LOG"
echo "Script: $SCRIPT" >> "$LOG"
echo >> "$LOG"

if [ ! -x "$SCRIPT" ]; then
  echo "ERREUR: script absent ou non exécutable: $SCRIPT" >> "$LOG"
  CODE=3
else
  "$SCRIPT" >> "$LOG" 2>&1
  CODE=$?
fi

python3 - "$STATUS" "$MODE" "$TITLE" "$CODE" "$LOG" <<'PY'
import json, sys, datetime, pathlib

status_path = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
title = sys.argv[3]
code = int(sys.argv[4])
log = sys.argv[5]
now = datetime.datetime.now().isoformat(timespec="seconds")

try:
    status = json.loads(status_path.read_text(encoding="utf-8"))
except Exception:
    status = {"events": []}

events = status.get("events") or []

if code == 0:
    msg = title + " terminée avec succès."
else:
    msg = f"{title} terminée avec erreur. Code: {code}"

events.append(f"[{now}] {msg}")
events.append(f"[{now}] Log: {log}")

status.update({
    "running": False,
    "done": True,
    "ok": code == 0,
    "mode": mode,
    "title": title,
    "message": msg,
    "finished_at": now,
    "returncode": code,
    "log": log,
    "events": events[-80:],
})

status_path.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
PY

exit "$CODE"

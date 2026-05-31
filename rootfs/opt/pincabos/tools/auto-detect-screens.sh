#!/bin/bash
set -e

LOG="/opt/pincabos/logs/updates/auto-detect-screens-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=================================================="
echo " PinCabOs - Auto-détection écrans"
echo "=================================================="

runuser -u pinball -- bash --noprofile --norc -lc '
export DISPLAY=:0
export XAUTHORITY=/home/pinball/.Xauthority
export XDG_RUNTIME_DIR=/run/user/1000

python3 <<PY
from screeninfo import get_monitors
from pathlib import Path
import json
import configparser

monitors = list(get_monitors())

if not monitors:
    raise SystemExit("ERREUR: aucun écran détecté.")

items = []
for idx, m in enumerate(monitors):
    area = int(m.width) * int(m.height)
    items.append({
        "id": idx,
        "name": getattr(m, "name", f"Screen-{idx}"),
        "x": int(m.x),
        "y": int(m.y),
        "width": int(m.width),
        "height": int(m.height),
        "area": area,
        "is_primary": bool(getattr(m, "is_primary", False)),
    })

# tri : plus grande surface en premier
sorted_items = sorted(items, key=lambda x: x["area"], reverse=True)

playfield = sorted_items[0]
backglass = sorted_items[1] if len(sorted_items) >= 2 else None
fulldmd = sorted_items[-1] if len(sorted_items) >= 3 else None

layout = {
    "playfield": playfield,
    "backglass": backglass,
    "fulldmd": fulldmd,
    "all_screens": sorted_items,
}

Path("/opt/pincabos/config").mkdir(parents=True, exist_ok=True)
Path("/opt/pincabos/config/screens/screens.json").write_text(json.dumps(layout, indent=2))

ini_path = Path("/home/pinball/.config/vpinfe/vpinfe.ini")

config = configparser.ConfigParser()
config.optionxform = str
config.read(ini_path)

if "Displays" not in config:
    config["Displays"] = {}

config["Displays"]["tablescreenid"] = str(playfield["id"])
config["Displays"]["tableorientation"] = "landscape"
config["Displays"]["tablerotation"] = "0"

if backglass:
    config["Displays"]["bgscreenid"] = str(backglass["id"])

if fulldmd:
    config["Displays"]["dmdscreenid"] = str(fulldmd["id"])

with ini_path.open("w") as f:
    config.write(f)

print("Écrans détectés:")
for s in sorted_items:
    print(f"  ID {s["id"]} - {s["name"]} - {s["width"]}x{s["height"]} - area={s["area"]}")

print()
print("Assignation automatique:")
print(f"  Playfield : écran {playfield["id"]} - {playfield["width"]}x{playfield["height"]}")
if backglass:
    print(f"  Backglass : écran {backglass["id"]} - {backglass["width"]}x{backglass["height"]}")
else:
    print("  Backglass : non détecté")

if fulldmd:
    print(f"  FullDMD   : écran {fulldmd["id"]} - {fulldmd["width"]}x{fulldmd["height"]}")
else:
    print("  FullDMD   : non détecté")

print()
print(f"Config VPinFE mise à jour: {ini_path}")
PY
'

chown -R pinball:pinball /opt/pincabos/config /home/pinball/.config/vpinfe

echo "=================================================="
echo "Auto-détection écrans terminée."
echo "=================================================="


# PINCABOS_PRIMARY_PLAYFIELD_LARGEST_PATCH_V3
# Playfield = primary si présent, sinon plus gros écran.
python3 <<'PYPIN'
import json
from pathlib import Path
from datetime import datetime

p = Path("/opt/pincabos/config/screens/screens.json")

try:
    data = json.loads(p.read_text(errors="replace"))
    screens = data.get("all_screens") or []

    if screens:
        selected = None
        reason = ""

        playfield = data.get("playfield")
        if isinstance(playfield, dict) and playfield.get("id") is not None:
            pf_id = int(playfield.get("id"))
            for screen in screens:
                if int(screen.get("id", -1)) == pf_id:
                    selected = screen
                    reason = "playfield"
                    break

        if selected is None:
            selected = max(screens, key=lambda screen: int(screen.get("area") or 0))
            reason = "largest_monitor"

        selected_id = int(selected.get("id"))

        for screen in screens:
            screen["is_primary"] = int(screen.get("id", -1)) == selected_id

        for role in ["playfield", "backglass", "fulldmd"]:
            obj = data.get(role)
            if isinstance(obj, dict):
                obj["is_primary"] = int(obj.get("id", -1)) == selected_id

        data["system_primary"] = {
            "id": selected.get("id"),
            "name": selected.get("name"),
            "x": selected.get("x"),
            "y": selected.get("y"),
            "width": selected.get("width"),
            "height": selected.get("height"),
            "area": selected.get("area"),
            "rule": reason,
            "updated_at": datetime.now().isoformat(timespec="seconds")
        }

        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        print("Primary screen rule applied:")
        print("rule=" + reason)
        print("id=" + str(selected.get("id")))
        print("name=" + str(selected.get("name")))

except Exception as e:
    print("WARNING primary patch v3:", e)
PYPIN


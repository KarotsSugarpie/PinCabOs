import shutil
import os
import time
from flask import request, redirect
import json
from pathlib import Path
import html
import re

# PinCabOS WebApp Tools module
# Dependencies:
# - Flask app object from /opt/pincabos/web/app.py
# - render_page callable from /opt/pincabos/web/app.py
# - Existing routes kept in app.py:
#   - /tools/commander
#   - /tools/external-disks
#   - /console
#   - /tables
#   - /import
#   - /gpu
#   - /audio-ssf
# Created by Karots Sugarpie

_TOOLS_PAGE_HELPER = None


def tools_hub_html():
    return r"""
<style>
.tools-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
  align-items: stretch;
}
.tools-col {
  background: rgba(18, 18, 24, 0.76);
  border: 1px solid rgba(255, 122, 0, 0.32);
  border-radius: 18px;
  padding: 18px;
  box-shadow: 0 0 18px rgba(0,0,0,0.25);
}
.tools-col h2 {
  margin: 0 0 8px 0;
  color: #ffb000;
  font-size: 22px;
}
.tools-col p.tools-intro {
  min-height: 45px;
  margin-top: 0;
  color: #ddd;
  font-size: 14px;
}
.tool-card {
  display: block;
  margin: 12px 0;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.13);
  background: rgba(255,255,255,0.045);
  text-decoration: none;
  color: inherit;
}
.tool-card:hover {
  border-color: rgba(255,122,0,0.75);
  background: rgba(255,122,0,0.10);
}
.tool-card strong {
  display: block;
  color: #ffffff;
  font-size: 16px;
  margin-bottom: 5px;
}
.tool-card span {
  display: block;
  color: #cccccc;
  font-size: 13px;
  line-height: 1.35;
}
.tool-card.disabled {
  opacity: 0.62;
  cursor: not-allowed;
}
.tool-card.disabled:hover {
  border-color: rgba(255,255,255,0.13);
  background: rgba(255,255,255,0.045);
}
.tool-badge {
  display: inline-block;
  margin-top: 8px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255,176,0,0.16);
  color: #ffb000;
  font-size: 12px;
}
@media (max-width: 1100px) {
  .tools-grid-3 {
    grid-template-columns: 1fr;
  }
  .tools-col p.tools-intro {
    min-height: auto;
  }
}
</style>

<h1>Outils PinCabOS</h1>
<p>Centre d’outils séparé en trois familles : système PinCabOS, frontend VPinFE, et moteur VPinballX.</p>

<div class="tools-grid-3">

  <section class="tools-col">
    <h2>Outils PinCabOS</h2>
    <p class="tools-intro">Gestion système, accès console, fichiers et périphériques externes.</p>

<a class="tool-card" href="/tools/import-table">
      <strong>Import de Tables Smart</strong>
      <span>Importer, analyser et préparer une table avec le système Smart PinCabOS.</span>
    </a>

<a class="tool-card" href="/tools/export-table">
      <strong>Export de Tables Smart PinCabOS</strong>
      <span>Préparer un export Smart PinCabOS avec table, médias et dépendances.</span>
    </a>


    <a class="tool-card" href="/tools/commander">
      <strong>Ouvrir PinCab Explorer</strong>
      <span>Explorateur Web pour parcourir, gérer, renommer, copier, archiver et préparer les fichiers PinCabOS.</span>
    </a>

    <a class="tool-card" href="/console">
      <strong>Ouvrir PinCab Console</strong>
      <span>Console Web locale pour administration et diagnostic rapide dans la même fenêtre.</span>
    </a>

    <a class="tool-card" href="/tools/external-disks">
      <strong>Gestion disques externes</strong>
      <span>USB, SMB, montages, détection et accès aux médias externes.</span>
    </a>
    <a class="tool-card" href="/tools/appearance">
      <strong>Apparence PinCabOS</strong>
      <span>Personnalisation visuelle du système : thème, fond d’écran, couleurs, logo, affichage WebApp et éléments cabinet.</span>
    </a>
  </section>

  <section class="tools-col">
    <h2>Outils VPinFE</h2>
    <p class="tools-intro">Frontend, import, tables, médias et configuration VPinFE.</p>
<a class="tool-card" href="/tools/vpinfe/ini">
      <strong>Config INI VPinFE</strong>
      <span>Lecture guidée de /home/pinball/.config/vpinfe/vpinfe.ini. Édition avec backup prévue en phase suivante.</span>
      <span class="tool-badge">Read-only</span>
    </a>


    <a class="tool-card" href="/tables">
      <strong>Tables VPinFE</strong>
      <span>Ouvrir la page de gestion des tables déjà existante.</span>
    </a>

    <a class="tool-card disabled" href="#" onclick="return false;">
      <strong>VPinFE en fenêtre</strong>
      <span>Ouverture des pages VPinFE existantes dans une fenêtre dédiée/iframe quand le proxy sera confirmé.</span>
      <span class="tool-badge">Phase 2</span>
    </a>
  </section>

  <section class="tools-col">
    <h2>Outils VPinballX</h2>
    <p class="tools-intro">VPX BGFX, chemins de tables, ROMs, médias par défaut et configuration moteur.</p>
<a class="tool-card" href="/tools/vpinballx/ini">
      <strong>Config INI VPinballX</strong>
      <span>Lecture guidée de /home/pinball/.vpinball/VPinballX.ini. Édition avec backup prévue en phase suivante.</span>
      <span class="tool-badge">Read-only</span>
    </a>


    <a class="tool-card" href="/gpu">
      <strong>Écrans / GPU / VPX</strong>
      <span>Configuration écrans, application vers VPinFE et VPinballX.ini.</span>
    </a>

    <a class="tool-card" href="/audio-ssf">
      <strong>Audio / SSF</strong>
      <span>Configuration audio, périphériques, tests ALSA et paramètres liés à VPinballX.</span>
    </a>

    <a class="tool-card" href="/tools/vpx-ball-cabinet">
      <strong>VPX Ball Cabinet</strong>
      <span>Outil existant pour configuration cabinet de la bille VPX.</span>
    </a>
  </section>

</div>
"""



def tools_page_html():
    body = tools_hub_html()
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Outils PinCabOS</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      margin: 0;
      padding: 24px;
      font-family: Arial, Helvetica, sans-serif;
      background: #0f1117;
      color: #f2f2f2;
    }}
    a {{
      color: inherit;
    }}
    code {{
      color: #ffb000;
    }}
  </style>
</head>
<body>
  <p><a href="/">← Retour dashboard</a></p>
  {body}
</body>
</html>"""

def register_tools_routes(app, page):
    global _TOOLS_PAGE_HELPER
    _TOOLS_PAGE_HELPER = page
    @app.route("/tools")
    def tools():
        return page("Outils", tools_hub_html())

    _tools_register_ini_readonly_routes(app)
    _tools_register_export_table_get_route(app)
    _tools_register_import_table_get_route(app)
    _tools_register_appearance_routes(app)
    _tools_register_appearance_write_routes(app)

# ---------------------------------------------------------------------------
# INI read-only viewer - Phase 2A
# Dependencies:
# - /home/pinball/.config/vpinfe/vpinfe.ini
# - /home/pinball/.vpinball/VPinballX.ini
# Created by Karots Sugarpie
# ---------------------------------------------------------------------------

PINCABOS_VPINFE_INI = Path("/home/pinball/.config/vpinfe/vpinfe.ini")
PINCABOS_VPINBALLX_INI = Path("/home/pinball/.vpinball/VPinballX.ini")


def _tools_esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _tools_read_ini_preserve_lines(path):
    path = Path(path)
    if not path.exists():
        return {
            "ok": False,
            "error": f"Fichier absent: {path}",
            "path": str(path),
            "sections": [],
            "raw_count": 0,
        }

    try:
        raw_lines = path.read_text(errors="replace").splitlines()
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Lecture impossible: {exc}",
            "path": str(path),
            "sections": [],
            "raw_count": 0,
        }

    sections = []
    current = {
        "name": "GLOBAL",
        "items": [],
    }

    def push_current():
        if current["items"] or current["name"] != "GLOBAL":
            sections.append({
                "name": current["name"],
                "items": list(current["items"]),
            })

    for idx, line in enumerate(raw_lines, start=1):
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            push_current()
            current = {
                "name": stripped[1:-1].strip() or "UNNAMED",
                "items": [],
            }
            continue

        if stripped.startswith("#") or stripped.startswith(";"):
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            current["items"].append({
                "line": idx,
                "key": key.strip(),
                "value": value.strip(),
            })
        else:
            current["items"].append({
                "line": idx,
                "key": stripped,
                "value": "",
            })

    push_current()

    return {
        "ok": True,
        "error": "",
        "path": str(path),
        "sections": sections,
        "raw_count": len(raw_lines),
    }


def _tools_ini_description(profile, section, key):
    s = (section or "").lower()
    k = (key or "").lower()

    descriptions = {
        "tables": "Chemin lié aux tables ou médias.",
        "table": "Chemin ou option liée aux tables.",
        "rom": "Chemin ou option liée aux ROMs / PinMAME.",
        "pinmame": "Chemin ou option liée à PinMAME.",
        "media": "Chemin ou option liée aux médias.",
        "image": "Chemin ou option liée aux images.",
        "sound": "Audio / périphérique sonore.",
        "music": "Musique / périphérique audio.",
        "dmd": "DMD / FullDMD / affichage score.",
        "fulldmd": "FullDMD.",
        "screen": "Écran / position / résolution.",
        "window": "Fenêtre / affichage.",
        "path": "Chemin de fichier ou dossier.",
        "dir": "Répertoire.",
        "directory": "Répertoire.",
        "dof": "DirectOutput Framework.",
        "b2s": "Backglass B2S.",
        "controller": "Contrôleur VPX / DOF / B2S.",
    }

    blob = f"{s} {k}"
    for token, desc in descriptions.items():
        if token in blob:
            return desc

    if profile == "vpinfe":
        return "Paramètre VPinFE."
    return "Paramètre VPinballX."



def _tools_ini_b2_profiles():
    return {
        "vpinfe": {
            "title": "VPinFE INI Studio",
            "subtitle": "Safe editor for VPinFE frontend settings. Only approved PinCabOS keys are editable here.",
            "path": Path("/home/pinball/.config/vpinfe/vpinfe.ini"),
            "route": "/tools/vpinfe/ini",
            "save_route": "/tools/vpinfe/ini/save",
            "source_note": "VPinFE uses vpinfe.ini as its frontend configuration file. PinCabOS keeps the official active config under /home/pinball/.config/vpinfe/vpinfe.ini.",
            "keys": [
                {
                    "section": "Displays",
                    "key": "cabmode",
                    "type": "bool",
                    "title": "Cabinet mode",
                    "description": "Enables cabinet-oriented display behavior. PinCabOS safe value is usually true for a real cabinet.",
                    "values": ["true", "false"],
                },
                {
                    "section": "Displays",
                    "key": "tablescreenid",
                    "type": "screen",
                    "title": "Table / playfield screen ID",
                    "description": "Screen ID used for the playfield/table display. In a standard PinCabOS cabinet this should normally be 0.",
                },
                {
                    "section": "Displays",
                    "key": "bgscreenid",
                    "type": "screen_empty",
                    "title": "Backglass screen ID",
                    "description": "Screen ID used for the backglass. Leave empty when no dedicated backglass screen is assigned.",
                },
                {
                    "section": "Displays",
                    "key": "dmdscreenid",
                    "type": "screen_empty",
                    "title": "DMD screen ID",
                    "description": "Screen ID used for DMD output. Leave empty when DMD is not mapped to a separate screen.",
                },
                {
                    "section": "Displays",
                    "key": "fulldmdscreenid",
                    "type": "screen_empty",
                    "title": "FullDMD screen ID",
                    "description": "Screen ID used for FullDMD output. PinCabOS commonly maps this to the third display when present.",
                },
                {
                    "section": "Settings",
                    "key": "vpxbinpath",
                    "type": "path",
                    "title": "VPX executable / wrapper path",
                    "description": "Path VPinFE launches for Visual Pinball. PinCabOS safe value is /opt/pincabos/bin/vpx.sh.",
                },
                {
                    "section": "Settings",
                    "key": "vpxinipath",
                    "type": "path",
                    "title": "VPinballX.ini path",
                    "description": "Path to the VPX settings file. VPinFE uses this path to locate VPX configuration and logs.",
                },
                {
                    "section": "Settings",
                    "key": "tablerootdir",
                    "type": "path",
                    "title": "Tables root directory",
                    "description": "Root folder scanned by VPinFE for VPX tables. PinCabOS safe value is /home/pinball/Tables.",
                },
                {
                    "section": "Settings",
                    "key": "muteaudio",
                    "type": "bool",
                    "title": "Mute VPinFE audio",
                    "description": "Controls VPinFE frontend audio muting. For a cabinet, PinCabOS usually keeps this false.",
                    "values": ["false", "true"],
                },
                {
                    "section": "Settings",
                    "key": "manageruiport",
                    "type": "port",
                    "title": "Manager UI port",
                    "description": "Local NiceGUI management UI port used by VPinFE. PinCabOS default is usually 8000.",
                },
                {
                    "section": "Settings",
                    "key": "themeassetsport",
                    "type": "port",
                    "title": "Theme assets port",
                    "description": "Local media/theme asset server port used by VPinFE. PinCabOS default is usually 8001.",
                },
            ],
        },
        "vpx": {
            "title": "VPinballX INI Studio",
            "subtitle": "Safe editor for core VPX standalone settings. Only approved PinCabOS keys are editable here.",
            "path": Path("/home/pinball/.vpinball/VPinballX.ini"),
            "route": "/tools/vpinballx/ini",
            "save_route": "/tools/vpinballx/ini/save",
            "source_note": "VPX stores settings in VPinballX.ini so they can be edited manually or by third-party tools and shared across standalone platforms.",
            "keys": [
                {
                    "section": "Player",
                    "key": "FullScreen",
                    "type": "bool01",
                    "title": "Fullscreen mode",
                    "description": "Runs VPX in fullscreen mode. PinCabOS cabinet mode should normally keep this enabled.",
                    "values": ["1", "0"],
                },
                {
                    "section": "Player",
                    "key": "ShowFPS",
                    "type": "bool01",
                    "title": "Show FPS",
                    "description": "Displays the frame-rate counter. Useful for debugging, normally disabled for a clean cabinet.",
                    "values": ["0", "1"],
                },
                {
                    "section": "Player",
                    "key": "Exitconfirm",
                    "type": "int",
                    "title": "Exit confirmation behavior",
                    "description": "VPX exit confirmation setting. Keep the current value unless you know the cabinet button workflow.",
                },
                {
                    "section": "Player",
                    "key": "DisableESC",
                    "type": "bool01",
                    "title": "Disable ESC",
                    "description": "Controls whether ESC behavior is disabled. Important for cabinet workflows to avoid accidental exits.",
                    "values": ["0", "1"],
                },
                {
                    "section": "Displays",
                    "key": "cabmode",
                    "type": "bool",
                    "title": "Cabinet mode",
                    "description": "Enables cabinet display behavior for VPX. PinCabOS safe value is usually true.",
                    "values": ["true", "false"],
                },
                {
                    "section": "Displays",
                    "key": "tablescreenid",
                    "type": "screen",
                    "title": "Playfield screen ID",
                    "description": "Screen ID used by VPX for the playfield/table. In PinCabOS this should normally be 0.",
                },
                {
                    "section": "Displays",
                    "key": "bgscreenid",
                    "type": "screen_empty",
                    "title": "Backglass screen ID",
                    "description": "Screen ID used by VPX for backglass-related output when available. Empty means not assigned.",
                },
                {
                    "section": "Displays",
                    "key": "dmdscreenid",
                    "type": "screen_empty",
                    "title": "DMD screen ID",
                    "description": "Screen ID used for DMD output. Empty means not assigned.",
                },
                {
                    "section": "Displays",
                    "key": "fulldmdscreenid",
                    "type": "screen_empty",
                    "title": "FullDMD screen ID",
                    "description": "Screen ID used for FullDMD output on a 3-screen cabinet.",
                },
                {
                    "section": "Displays",
                    "key": "tableorientation",
                    "type": "choice",
                    "title": "Playfield orientation",
                    "description": "Orientation label used by PinCabOS screen tooling. Common values are landscape or portrait.",
                    "values": ["landscape", "portrait"],
                },
                {
                    "section": "Displays",
                    "key": "tablerotation",
                    "type": "choice",
                    "title": "Playfield rotation",
                    "description": "Rotation value used by PinCabOS screen tooling. Common values are 0, 90, 180, 270.",
                    "values": ["0", "90", "180", "270"],
                },
            ],
        },
    }


def _tools_ini_b2_read_value(lines, section, key):
    current = ""
    wanted_section = str(section).lower()
    wanted_key = str(key).lower()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip().lower()
            continue
        if current == wanted_section and "=" in line:
            k, v = line.split("=", 1)
            if k.strip().lower() == wanted_key:
                return v.strip()
    return ""


def _tools_ini_b2_validate_value(meta, value):
    value = str(value or "").strip()
    typ = meta.get("type", "text")

    if typ == "bool":
        if value.lower() not in {"true", "false"}:
            raise ValueError(f"{meta['section']}.{meta['key']} must be true or false")
        return value.lower()

    if typ == "bool01":
        if value not in {"0", "1"}:
            raise ValueError(f"{meta['section']}.{meta['key']} must be 0 or 1")
        return value

    if typ == "int":
        if not re.fullmatch(r"-?[0-9]+", value):
            raise ValueError(f"{meta['section']}.{meta['key']} must be an integer")
        return value

    if typ == "screen":
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError(f"{meta['section']}.{meta['key']} must be a screen number")
        return value

    if typ == "screen_empty":
        if value == "":
            return ""
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError(f"{meta['section']}.{meta['key']} must be empty or a screen number")
        return value

    if typ == "path":
        if not value.startswith("/"):
            raise ValueError(f"{meta['section']}.{meta['key']} must be an absolute path")
        return value

    if typ == "port":
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError(f"{meta['section']}.{meta['key']} must be a port number")
        port = int(value)
        if port < 1 or port > 65535:
            raise ValueError(f"{meta['section']}.{meta['key']} port must be between 1 and 65535")
        return str(port)

    if typ == "choice":
        allowed = [str(x) for x in meta.get("values", [])]
        if value not in allowed:
            raise ValueError(f"{meta['section']}.{meta['key']} must be one of: {', '.join(allowed)}")
        return value

    return value


def _tools_ini_b2_set_key(lines, section, key, value):
    section = str(section)
    key = str(key)
    current = None
    sec_start = None
    sec_end = len(lines)

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            name = stripped[1:-1].strip()
            if current == section and sec_end == len(lines):
                sec_end = idx
                break
            current = name
            if name.lower() == section.lower():
                sec_start = idx
                sec_end = len(lines)

    if sec_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        lines.append(f"{key} = {value}")
        return lines

    for idx in range(sec_start + 1, sec_end):
        line = lines[idx]
        if "=" not in line:
            continue
        k, _v = line.split("=", 1)
        if k.strip().lower() == key.lower():
            lines[idx] = f"{key} = {value}"
            return lines

    insert_at = sec_end
    lines.insert(insert_at, f"{key} = {value}")
    return lines


def _tools_ini_b2_backup(path):
    src = Path(path)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst_dir = Path("/opt/pincabos/backups") / f"ini-pages-write-{stamp}"
    dst_dir.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dst_dir / (src.name + ".before"))
    return dst_dir


def _tools_ini_b2_save(profile_key):
    profiles = _tools_ini_b2_profiles()
    if profile_key not in profiles:
        raise ValueError("Unknown INI profile")

    profile = profiles[profile_key]
    path = Path(profile["path"])
    lines = path.read_text(errors="replace").splitlines() if path.exists() else []
    backup_dir = _tools_ini_b2_backup(path)

    changed = []
    for meta in profile["keys"]:
        field = f"ini__{meta['section']}__{meta['key']}"
        if field not in request.form:
            continue
        new_value = _tools_ini_b2_validate_value(meta, request.form.get(field, ""))
        old_value = _tools_ini_b2_read_value(lines, meta["section"], meta["key"])
        if old_value != new_value:
            lines = _tools_ini_b2_set_key(lines, meta["section"], meta["key"], new_value)
            changed.append((meta["section"], meta["key"], old_value, new_value))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        uid = 1000
        gid = 1000
        os.chown(path, uid, gid)
    except Exception:
        pass

    return backup_dir, changed


def _tools_ini_page_html(title, subtitle, profile, ini_path):
    path = Path(ini_path)
    exists = path.exists()

    try:
        raw_lines = path.read_text(errors="replace").splitlines() if exists else []
        read_error = ""
    except Exception as exc:
        raw_lines = []
        read_error = str(exc)

    profiles = _tools_ini_b2_profiles()
    edit_profile = profiles.get(profile, {})
    editable_keys = edit_profile.get("keys", [])
    editable_map = {
        (meta["section"].lower(), meta["key"].lower()): meta
        for meta in editable_keys
    }

    safe_defaults = {
        ("vpinfe", "Displays", "cabmode"): "true",
        ("vpinfe", "Displays", "tablescreenid"): "0",
        ("vpinfe", "Displays", "bgscreenid"): "",
        ("vpinfe", "Displays", "dmdscreenid"): "",
        ("vpinfe", "Displays", "fulldmdscreenid"): "2",
        ("vpinfe", "Settings", "vpxbinpath"): "/opt/pincabos/bin/vpx.sh",
        ("vpinfe", "Settings", "vpxinipath"): "/home/pinball/.vpinball/VPinballX.ini",
        ("vpinfe", "Settings", "tablerootdir"): "/home/pinball/Tables",
        ("vpinfe", "Settings", "muteaudio"): "false",
        ("vpinfe", "Settings", "manageruiport"): "8000",
        ("vpinfe", "Settings", "themeassetsport"): "8001",

        ("vpx", "Player", "FullScreen"): "1",
        ("vpx", "Player", "ShowFPS"): "0",
        ("vpx", "Player", "Exitconfirm"): "120",
        ("vpx", "Player", "DisableESC"): "0",
        ("vpx", "Displays", "cabmode"): "true",
        ("vpx", "Displays", "tablescreenid"): "0",
        ("vpx", "Displays", "bgscreenid"): "",
        ("vpx", "Displays", "dmdscreenid"): "",
        ("vpx", "Displays", "fulldmdscreenid"): "2",
        ("vpx", "Displays", "tableorientation"): "landscape",
        ("vpx", "Displays", "tablerotation"): "0",
    }

    friendly_names = {
        "cabmode": "Cabinet mode",
        "tablescreenid": "Playfield screen",
        "bgscreenid": "Backglass screen",
        "dmdscreenid": "DMD screen",
        "fulldmdscreenid": "FullDMD screen",
        "vpxbinpath": "VPX launcher",
        "vpxinipath": "VPX INI file",
        "tablerootdir": "Tables folder",
        "muteaudio": "Mute frontend audio",
        "manageruiport": "Manager UI port",
        "themeassetsport": "Theme assets port",
        "FullScreen": "Fullscreen",
        "ShowFPS": "Show FPS",
        "Exitconfirm": "Exit confirmation",
        "DisableESC": "Disable ESC",
        "tableorientation": "Playfield orientation",
        "tablerotation": "Playfield rotation",
    }

    path_suggestions = {
        "vpxbinpath": [
            "/opt/pincabos/bin/vpx.sh",
            "/opt/pincabos/apps/vpinball/VPinballX",
            "/opt/pincabos/apps/vpinball/VPinballX-BGFX",
        ],
        "vpxinipath": [
            "/home/pinball/.vpinball/VPinballX.ini",
        ],
        "tablerootdir": [
            "/home/pinball/Tables",
            "/home/pinball/Visual Pinball/Tables",
            "/mnt/tables",
        ],
    }

    sections = []
    current = {"name": "Sans section", "items": [], "comments": []}

    def push_current():
        if current["items"] or current["comments"] or current["name"] != "Sans section":
            sections.append({
                "name": current["name"],
                "items": list(current["items"]),
                "comments": list(current["comments"]),
            })

    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
            push_current()
            current = {"name": stripped[1:-1].strip(), "items": [], "comments": []}
            continue

        if not stripped:
            continue

        if stripped.startswith("#") or stripped.startswith(";"):
            if len(current["comments"]) < 6:
                current["comments"].append(stripped)
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            desc = ""
            try:
                desc = _tools_ini_description(profile, current["name"], key)
            except Exception:
                desc = ""

            meta = editable_map.get((current["name"].lower(), key.lower()))
            if meta and meta.get("description"):
                desc = meta.get("description")

            current["items"].append({
                "key": key,
                "value": value,
                "desc": desc,
                "editable": bool(meta),
                "meta": meta,
            })
        else:
            if len(current["comments"]) < 6:
                current["comments"].append(stripped)

    push_current()

    existing_pairs = {
        (sec["name"].lower(), item["key"].lower())
        for sec in sections
        for item in sec["items"]
    }

    for meta in editable_keys:
        pair = (meta["section"].lower(), meta["key"].lower())
        if pair in existing_pairs:
            continue
        found = None
        for sec in sections:
            if sec["name"].lower() == meta["section"].lower():
                found = sec
                break
        if not found:
            found = {"name": meta["section"], "items": [], "comments": []}
            sections.append(found)
        found["items"].append({
            "key": meta["key"],
            "value": "",
            "desc": meta.get("description", ""),
            "editable": True,
            "meta": meta,
        })

    key_count = sum(len(sec["items"]) for sec in sections)
    editable_count = sum(1 for sec in sections for item in sec["items"] if item.get("editable"))
    section_count = len(sections)

    size_text = "absent"
    mtime_text = "absent"
    if exists:
        try:
            st = path.stat()
            size_text = f"{st.st_size:,} octets".replace(",", " ")
            mtime_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        except Exception:
            size_text = "lecture impossible"
            mtime_text = "lecture impossible"

    status_badge = "<span class='ok'>présent</span>" if exists else "<span class='bad'>absent</span>"
    if read_error:
        status_badge = "<span class='bad'>erreur lecture</span>"

    saved_html = ""
    if request.args.get("saved"):
        saved_html = "<div class='card'><p class='ok'>GO: INI saved with automatic backup.</p></div>"
    if request.args.get("nochange"):
        saved_html = "<div class='card'><p class='warn'>No change detected. INI left untouched except backup check.</p></div>"

    form_id = "pcoIniSafeEditor"
    save_route = edit_profile.get("save_route", "")
    section_nav = []
    section_cards = []

    def section_color_class(name, idx):
        palette = [
            "sec-orange", "sec-purple", "sec-blue", "sec-cyan",
            "sec-green", "sec-pink", "sec-red", "sec-gold",
        ]
        important = {
            "player": "sec-orange",
            "settings": "sec-purple",
            "displays": "sec-cyan",
            "controller": "sec-blue",
            "dmd": "sec-pink",
            "sound": "sec-green",
            "audio": "sec-green",
            "bgfx": "sec-gold",
            "plugin.dof": "sec-red",
        }
        low = name.lower()
        return important.get(low, palette[idx % len(palette)])

    def default_value(sec_name, key):
        return safe_defaults.get((profile, sec_name, key), "—")

    def function_name(key):
        return friendly_names.get(key, key)

    def input_html(sec_name, item):
        meta = item.get("meta") or {}
        field = f"ini__{sec_name}__{item['key']}"
        value = item["value"]
        typ = meta.get("type", "text")
        values = meta.get("values") or []

        if values:
            options = []
            if typ == "screen_empty" and "" not in values:
                options.append(f'<option value=""{" selected" if value == "" else ""}>(empty)</option>')
            for opt in values:
                sel = " selected" if str(opt) == str(value) else ""
                label = "(empty)" if str(opt) == "" else str(opt)
                options.append(f'<option value="{_tools_esc(opt)}"{sel}>{_tools_esc(label)}</option>')
            return f'<select name="{_tools_esc(field)}">{"".join(options)}</select>'

        if typ in {"bool", "bool01", "choice"}:
            return f'<input type="text" name="{_tools_esc(field)}" value="{_tools_esc(value)}">'

        if typ == "path":
            list_id = "dl-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", field)
            opts = "".join(
                f'<option value="{_tools_esc(v)}"></option>'
                for v in path_suggestions.get(item["key"], [])
            )
            return f'<input type="text" name="{_tools_esc(field)}" value="{_tools_esc(value)}" list="{_tools_esc(list_id)}"><datalist id="{_tools_esc(list_id)}">{opts}</datalist>'

        if typ in {"screen", "screen_empty"}:
            if typ == "screen_empty":
                options = ['<option value="">(empty)</option>'] + [
                    f'<option value="{i}"{" selected" if value == str(i) else ""}>Screen {i}</option>'
                    for i in range(0, 8)
                ]
                if value not in {"", "0", "1", "2", "3", "4", "5", "6", "7"}:
                    options.append(f'<option value="{_tools_esc(value)}" selected>{_tools_esc(value)}</option>')
                return f'<select name="{_tools_esc(field)}">{"".join(options)}</select>'
            options = [
                f'<option value="{i}"{" selected" if value == str(i) else ""}>Screen {i}</option>'
                for i in range(0, 8)
            ]
            if value not in {"0", "1", "2", "3", "4", "5", "6", "7"} and value != "":
                options.append(f'<option value="{_tools_esc(value)}" selected>{_tools_esc(value)}</option>')
            return f'<select name="{_tools_esc(field)}">{"".join(options)}</select>'

        if typ == "port":
            return f'<input type="number" min="1" max="65535" name="{_tools_esc(field)}" value="{_tools_esc(value)}">'

        if typ == "int":
            return f'<input type="number" name="{_tools_esc(field)}" value="{_tools_esc(value)}">'

        return f'<input type="text" name="{_tools_esc(field)}" value="{_tools_esc(value)}">'

    for idx, sec in enumerate(sections):
        sec_name = sec["name"]
        sec_class = section_color_class(sec_name, idx)
        sec_id = "ini-sec-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", sec_name).strip("-").lower()
        if not sec_id or sec_id == "ini-sec-":
            sec_id = f"ini-sec-{idx}"

        section_nav.append(
            f'<a class="pco-ini-nav-chip {sec_class}" href="#{_tools_esc(sec_id)}">'
            f'<span class="dot"></span>{_tools_esc(sec_name)} <strong>{len(sec["items"])}</strong></a>'
        )

        comments_html = ""
        if sec["comments"]:
            comments_html = "<div class='pco-ini-comments'>" + "".join(
                f"<code>{_tools_esc(c)}</code>" for c in sec["comments"]
            ) + "</div>"

        rows = []
        for item in sec["items"]:
            key = item["key"]
            value = item["value"]
            shown_value = "(empty)" if value == "" else value
            desc = item["desc"] or "No description available yet for this key."
            meta = item.get("meta") or {}
            editable = item.get("editable")

            default = default_value(sec_name, key)
            default_display = "(empty)" if default == "" else default

            if editable:
                edit_cell = input_html(sec_name, item)
                edit_badge = "<span class='pco-ini-editable'>editable</span>"
            else:
                edit_cell = f"<span class='pco-ini-current-only'><code>{_tools_esc(shown_value)}</code></span>"
                edit_badge = "<span class='pco-ini-readonly'>read-only</span>"

            value_type = meta.get("type", "read-only")
            rows.append(f"""
<tr class="{'editable-row' if editable else 'readonly-row'}">
  <td class="col-function">
    <div class="function-main">{_tools_esc(function_name(key))}</div>
    <div class="function-key"><code>{_tools_esc(sec_name)}.{_tools_esc(key)}</code> {edit_badge}</div>
  </td>
  <td class="col-default">
    <code>{_tools_esc(default_display)}</code>
    <div class="cell-note">PinCabOS safe/default</div>
  </td>
  <td class="col-edit">
    {edit_cell}
    <div class="cell-note">Current: <code>{_tools_esc(shown_value)}</code> · Type: <code>{_tools_esc(value_type)}</code></div>
  </td>
  <td class="col-desc">
    {_tools_esc(desc)}
  </td>
</tr>
""")

        table_html = f"""
<div class="pco-ini-table-wrap">
<table class="pco-ini-excel">
  <thead>
    <tr>
      <th>Function</th>
      <th>Default / safe value</th>
      <th>Editable value</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
</div>
"""

        section_cards.append(f"""
<div class="card pco-ini-section {sec_class}" id="{_tools_esc(sec_id)}">
  <div class="pco-ini-section-head">
    <h2><span></span>[{_tools_esc(sec_name)}]</h2>
    <strong>{len(sec["items"])} key(s)</strong>
  </div>
  {comments_html}
  {table_html}
</div>
""")

    raw_preview = "\n".join(raw_lines)
    if len(raw_preview) > 20000:
        raw_preview = raw_preview[:20000] + "\n\n--- aperçu tronqué ---"

    body = f"""
<style>
.pco-ini-hero {{
  display:grid;
  grid-template-columns: 1.25fr .75fr;
  gap:16px;
  align-items:stretch;
}}
.pco-ini-title {{
  margin:0 0 8px 0;
  font-size:30px;
  letter-spacing:.2px;
}}
.pco-ini-subtitle {{
  margin:0;
  opacity:.88;
  line-height:1.45;
}}
.pco-ini-path {{
  display:flex;
  gap:8px;
  align-items:center;
  flex-wrap:wrap;
  margin-top:12px;
}}
.pco-ini-path code {{
  white-space:normal;
  word-break:break-all;
}}
.pco-ini-kpis {{
  display:grid;
  grid-template-columns: repeat(2, minmax(0,1fr));
  gap:10px;
}}
.pco-ini-kpi {{
  padding:12px;
  border:1px solid var(--pco-appearance-card-border, rgba(255,122,0,.35));
  border-radius:14px;
  background:rgba(0,0,0,.18);
}}
.pco-ini-kpi strong {{
  display:block;
  font-size:22px;
  margin-bottom:4px;
}}
.pco-ini-kpi span {{
  opacity:.8;
  font-size:13px;
}}
.pco-ini-sticky {{
  position:sticky;
  top:8px;
  z-index:20;
  border:1px solid var(--pco-appearance-card-border, rgba(255,122,0,.45));
  box-shadow:0 12px 34px rgba(0,0,0,.32);
  backdrop-filter: blur(10px);
}}
.pco-ini-sticky-grid {{
  display:grid;
  grid-template-columns: 1fr auto;
  gap:12px;
  align-items:start;
}}
.pco-ini-toolbar {{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  align-items:center;
}}
.pco-ini-search {{
  min-width:300px;
  flex:1;
}}
.pco-ini-nav {{
  display:flex;
  gap:7px;
  flex-wrap:wrap;
  max-height:120px;
  overflow:auto;
  padding:4px 2px;
}}
.pco-ini-nav-chip {{
  display:inline-flex;
  gap:6px;
  align-items:center;
  padding:6px 9px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.16);
  text-decoration:none;
  background:rgba(0,0,0,.22);
  font-size:13px;
}}
.pco-ini-nav-chip strong {{
  opacity:.74;
}}
.pco-ini-nav-chip .dot {{
  width:8px;
  height:8px;
  border-radius:50%;
  display:inline-block;
}}
.sec-orange .dot, .pco-ini-section.sec-orange .pco-ini-section-head h2 span {{ background:#ff8c00; }}
.sec-purple .dot, .pco-ini-section.sec-purple .pco-ini-section-head h2 span {{ background:#9b5cff; }}
.sec-blue .dot, .pco-ini-section.sec-blue .pco-ini-section-head h2 span {{ background:#448cff; }}
.sec-cyan .dot, .pco-ini-section.sec-cyan .pco-ini-section-head h2 span {{ background:#00e5ff; }}
.sec-green .dot, .pco-ini-section.sec-green .pco-ini-section-head h2 span {{ background:#00ff99; }}
.sec-pink .dot, .pco-ini-section.sec-pink .pco-ini-section-head h2 span {{ background:#ff72c8; }}
.sec-red .dot, .pco-ini-section.sec-red .pco-ini-section-head h2 span {{ background:#ff4444; }}
.sec-gold .dot, .pco-ini-section.sec-gold .pco-ini-section-head h2 span {{ background:#ffcc33; }}

.pco-ini-section {{
  overflow:hidden;
}}
.pco-ini-section-head {{
  display:flex;
  justify-content:space-between;
  gap:12px;
  align-items:center;
  border-bottom:1px solid rgba(255,255,255,.10);
  padding-bottom:10px;
  margin-bottom:12px;
}}
.pco-ini-section-head h2 {{
  display:flex;
  gap:10px;
  align-items:center;
  margin:0;
}}
.pco-ini-section-head h2 span {{
  width:12px;
  height:12px;
  border-radius:50%;
  display:inline-block;
  box-shadow:0 0 14px currentColor;
}}
.pco-ini-comments {{
  display:flex;
  flex-direction:column;
  gap:4px;
  margin:0 0 10px 0;
  opacity:.72;
}}
.pco-ini-table-wrap {{
  overflow:auto;
  border:1px solid rgba(255,255,255,.12);
  border-radius:14px;
}}
.pco-ini-excel {{
  width:100%;
  border-collapse:separate;
  border-spacing:0;
  table-layout:fixed;
}}
.pco-ini-excel th {{
  position:sticky;
  top:0;
  z-index:2;
  text-align:left;
  padding:11px 12px;
  background:rgba(0,0,0,.45);
  border-bottom:1px solid rgba(255,255,255,.18);
  font-size:13px;
  text-transform:uppercase;
  letter-spacing:.5px;
}}
.pco-ini-excel td {{
  padding:11px 12px;
  border-bottom:1px solid rgba(255,255,255,.075);
  vertical-align:top;
}}
.pco-ini-excel tbody tr:nth-child(odd) td {{
  background:rgba(255,255,255,.035);
}}
.pco-ini-excel tbody tr:nth-child(even) td {{
  background:rgba(0,0,0,.12);
}}
.pco-ini-excel tbody tr.editable-row td {{
  box-shadow:inset 3px 0 0 rgba(0,255,153,.36);
}}
.pco-ini-excel tbody tr.readonly-row td {{
  opacity:.84;
}}
.col-function {{ width:24%; }}
.col-default {{ width:18%; }}
.col-edit {{ width:24%; }}
.col-desc {{ width:34%; line-height:1.42; }}

.function-main {{
  font-size:15px;
  font-weight:800;
  margin-bottom:4px;
}}
.function-key {{
  font-size:12px;
  opacity:.82;
  display:flex;
  gap:8px;
  flex-wrap:wrap;
  align-items:center;
}}
.cell-note {{
  margin-top:5px;
  font-size:12px;
  opacity:.68;
  line-height:1.35;
}}
.pco-ini-editable, .pco-ini-readonly {{
  display:inline-flex;
  padding:2px 7px;
  border-radius:999px;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.35px;
}}
.pco-ini-editable {{
  background:rgba(0,255,153,.13);
  border:1px solid rgba(0,255,153,.45);
  color:var(--pco-appearance-ok, #00ff99);
}}
.pco-ini-readonly {{
  background:rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.18);
  opacity:.72;
}}
.col-edit input,
.col-edit select {{
  width:100%;
  min-height:38px;
  box-sizing:border-box;
}}
.pco-ini-current-only code {{
  display:block;
  padding:9px 10px;
  border:1px solid rgba(255,255,255,.12);
  border-radius:10px;
  background:rgba(0,0,0,.18);
  white-space:normal;
  word-break:break-word;
}}
.pco-ini-raw pre {{
  max-height:360px;
  overflow:auto;
  white-space:pre-wrap;
  word-break:break-word;
}}
@media (max-width: 1100px) {{
  .pco-ini-hero,
  .pco-ini-sticky-grid {{
    grid-template-columns:1fr;
  }}
  .pco-ini-excel {{
    min-width:980px;
  }}
}}
</style>

{saved_html}

<div class="pco-ini-hero">
  <div class="card">
    <h1 class="pco-ini-title">{_tools_esc(title)}</h1>
    <p class="pco-ini-subtitle">{_tools_esc(subtitle)}</p>
    <p style="opacity:.82;margin-top:10px;">{_tools_esc(edit_profile.get("source_note", ""))}</p>
    <div class="pco-ini-path">
      <strong>File:</strong>
      <code id="pcoIniPath">{_tools_esc(str(path))}</code>
      <button class="button secondary" type="button" onclick="navigator.clipboard && navigator.clipboard.writeText(document.getElementById('pcoIniPath').innerText)">Copy path</button>
    </div>
  </div>

  <div class="card">
    <div class="pco-ini-kpis">
      <div class="pco-ini-kpi"><strong>{status_badge}</strong><span>Status</span></div>
      <div class="pco-ini-kpi"><strong>{section_count}</strong><span>Sections</span></div>
      <div class="pco-ini-kpi"><strong>{key_count}</strong><span>Total keys</span></div>
      <div class="pco-ini-kpi"><strong>{editable_count}</strong><span>Safe editable</span></div>
    </div>
  </div>
</div>

<form id="{_tools_esc(form_id)}" method="post" action="{_tools_esc(save_route)}">
  <div class="card pco-ini-sticky">
    <div class="pco-ini-sticky-grid">
      <div>
        <h2 style="margin:0 0 8px 0;">Navigation + Safe editor</h2>
        <div class="pco-ini-toolbar">
          <input class="pco-ini-search" id="pcoIniSearch" type="search" placeholder="Filter a section, function, key, value or description...">
          <button class="button secondary" type="button" onclick="document.getElementById('pcoIniSearch').value=''; pcoIniFilter();">Reset filter</button>
        </div>
        <p style="opacity:.78;margin:8px 0;">Last modified: <code>{_tools_esc(mtime_text)}</code> · Size: <code>{_tools_esc(size_text)}</code></p>
        <div class="pco-ini-nav">
          {''.join(section_nav)}
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end;">
        <button class="button" type="submit" onclick="return confirm('Save approved INI changes with automatic backup?');">Save approved changes</button>
        <a class="button secondary" href="{_tools_esc(edit_profile.get("route", ""))}">Reload</a>
      </div>
    </div>
  </div>

  <div id="pcoIniSections">
    {''.join(section_cards)}
  </div>
</form>

<div class="card pco-ini-raw">
  <h2>Raw preview</h2>
  <p>Read-only raw view for audit. Use the safe editor above to change approved keys.</p>
  <details>
    <summary class="button secondary" style="display:inline-block;cursor:pointer;">Show raw file</summary>
    <pre>{_tools_esc(raw_preview)}</pre>
  </details>
</div>

<script>
function pcoIniFilter() {{
  const q = (document.getElementById('pcoIniSearch').value || '').toLowerCase();
  document.querySelectorAll('.pco-ini-section').forEach(card => {{
    const txt = card.innerText.toLowerCase();
    card.style.display = txt.includes(q) ? '' : 'none';
  }});
}}
document.addEventListener('input', function(ev) {{
  if (ev.target && ev.target.id === 'pcoIniSearch') pcoIniFilter();
}});
</script>
"""
    return _tools_wrap_page("Outils", body)


def _tools_wrap_page(title, body):
    if _TOOLS_PAGE_HELPER is not None:
        return _TOOLS_PAGE_HELPER(title, body)

    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>{_tools_esc(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
{body}
</body>
</html>"""


def _tools_register_ini_readonly_routes(app):
    @app.route("/tools/vpinfe/ini")
    def tools_vpinfe_ini():
        profiles = _tools_ini_b2_profiles()
        p = profiles["vpinfe"]
        return _tools_ini_page_html(
            p["title"],
            p["subtitle"],
            "vpinfe",
            p["path"],
        )

    @app.route("/tools/vpinballx/ini")
    def tools_vpinballx_ini():
        profiles = _tools_ini_b2_profiles()
        p = profiles["vpx"]
        return _tools_ini_page_html(
            p["title"],
            p["subtitle"],
            "vpx",
            p["path"],
        )

    @app.route("/tools/vpinfe/ini/save", methods=["POST"])
    def tools_vpinfe_ini_save():
        try:
            _backup_dir, changed = _tools_ini_b2_save("vpinfe")
            suffix = "saved=1" if changed else "nochange=1"
            return redirect(f"/tools/vpinfe/ini?{suffix}")
        except Exception as exc:
            return _tools_wrap_page("Outils", f"<h1>VPinFE INI Studio</h1><div class='card'><h2>NOGOOD save</h2><p class='bad'>{_tools_esc(exc)}</p><p><a class='button secondary' href='/tools/vpinfe/ini'>Back</a></p></div>"), 400

    @app.route("/tools/vpinballx/ini/save", methods=["POST"])
    def tools_vpinballx_ini_save():
        try:
            _backup_dir, changed = _tools_ini_b2_save("vpx")
            suffix = "saved=1" if changed else "nochange=1"
            return redirect(f"/tools/vpinballx/ini?{suffix}")
        except Exception as exc:
            return _tools_wrap_page("Outils", f"<h1>VPinballX INI Studio</h1><div class='card'><h2>NOGOOD save</h2><p class='bad'>{_tools_esc(exc)}</p><p><a class='button secondary' href='/tools/vpinballx/ini'>Back</a></p></div>"), 400

# ---------------------------------------------------------------------------
# Export table GET landing page
# Dependencies:
# - Existing POST route in /opt/pincabos/web/app.py: /tools/export-table
# - Tables directory: /home/pinball/Tables
# Created by Karots Sugarpie
# ---------------------------------------------------------------------------

def _tools_list_table_dirs_for_export():
    root = Path("/home/pinball/Tables")
    rows = []
    try:
        if root.exists():
            for child in sorted(root.iterdir(), key=lambda x: x.name.lower()):
                if child.is_dir() and not child.name.startswith("."):
                    rows.append(child)
    except Exception:
        rows = []
    return rows


def _tools_export_table_get_html():
    tables = _tools_list_table_dirs_for_export()

    options = []
    for table_dir in tables:
        name = table_dir.name
        value = str(table_dir)
        options.append(
            f"<option value=\"{_tools_esc(value)}\">{_tools_esc(name)} — {_tools_esc(value)}</option>"
        )

    if options:
        options_html = "".join(options)
        select_html = f"""
<div class="card" style="max-width:920px;">
  <h2>Exporter une table</h2>
  <p>Choisis une table installée. Cette page ouvre proprement l’export depuis un clic normal.</p>

  <form method="post" action="/tools/export-table">
    <label>Table à exporter<br>
      <select id="pcoExportTableSelect" name="table_dir" style="width:100%;padding:10px;margin-top:6px;">
        {options_html}
      </select>
    </label>

    <input type="hidden" name="table" id="pcoExportTableHidden">
    <input type="hidden" name="table_name" id="pcoExportTableNameHidden">
    <input type="hidden" name="table_folder" id="pcoExportTableFolderHidden">
    <input type="hidden" name="table_path" id="pcoExportTablePathHidden">

    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
      <button class="button" type="submit">Préparer l’export</button>
      <a class="button secondary" href="/tools">Retour Outils</a>
      <a class="button secondary" href="/tools/commander">Ouvrir PinCab Explorer</a>
    </div>
  </form>

  <p class="warn" style="margin-top:12px;">
    Cette page GET ne modifie rien directement. Le vrai export reste traité par la route POST existante.
  </p>
</div>

<script>
(function(){{
  function syncExportFields() {{
    var sel = document.getElementById("pcoExportTableSelect");
    if (!sel) return;
    var value = sel.value || "";
    var parts = value.split("/").filter(Boolean);
    var name = parts.length ? parts[parts.length - 1] : value;

    var map = {{
      "pcoExportTableHidden": value,
      "pcoExportTableNameHidden": name,
      "pcoExportTableFolderHidden": name,
      "pcoExportTablePathHidden": value
    }};

    Object.keys(map).forEach(function(id){{
      var el = document.getElementById(id);
      if (el) el.value = map[id];
    }});
  }}

  var sel = document.getElementById("pcoExportTableSelect");
  if (sel) {{
    sel.addEventListener("change", syncExportFields);
    syncExportFields();
  }}
}})();
</script>
"""
    else:
        select_html = """
<div class="card">
  <h2>Aucune table détectée</h2>
  <p class="warn">Aucun dossier de table n’a été trouvé dans <code>/home/pinball/Tables</code>.</p>
  <p>
    <a class="button" href="/tools/commander">Ouvrir PinCab Explorer</a>
    <a class="button secondary" href="/tools">Retour Outils</a>
  </p>
</div>
"""

    return f"""
<h1>Export de table</h1>

<div class="grid">
  {select_html}

  <div class="card">
    <h2>Info</h2>
    <table>
      <tr><td>Page GET</td><td><span class="ok">OK</span></td></tr>
      <tr><td>Route réelle d’export</td><td><code>POST /tools/export-table</code></td></tr>
      <tr><td>Dossier tables</td><td><code>/home/pinball/Tables</code></td></tr>
    </table>
  </div>
</div>
"""


def _tools_register_export_table_get_route(app):
    @app.route("/tools/export-table", methods=["GET"])
    def tools_export_table_get():
        if _TOOLS_PAGE_HELPER is not None:
            return _TOOLS_PAGE_HELPER("Outils", _tools_export_table_get_html())
        return _tools_export_table_get_html()

# ---------------------------------------------------------------------------
# Import table GET landing page
# Dependencies:
# - Existing POST route in /opt/pincabos/web/app.py: /tools/import-table/analyze
# - Existing POST route in /opt/pincabos/web/app.py: /tools/import-table/install
# Created by Karots Sugarpie
# ---------------------------------------------------------------------------

def _tools_import_table_get_html():
    return """
<h1>Import de Tables Smart</h1>

<div class="grid">
  <div class="card" style="max-width:920px;">
    <h2>Importer une table</h2>
    <p>
      Cette page sert de porte d’entrée Smart pour importer une table PinCabOS.
      Elle utilise les routes d’analyse et d’installation déjà présentes dans la WebApp.
    </p>

    <form method="post" action="/tools/import-table/analyze" enctype="multipart/form-data">
      <label>Archive ou fichier de table<br>
        <input type="file" name="packages" multiple style="width:100%;padding:10px;margin-top:6px;">
      </label>

      <p class="warn" style="margin-top:10px;">
        Si l’analyse ne détecte pas le fichier, on ajustera le nom du champ selon la route existante.
        Cette page GET ne modifie rien directement.
      </p>

      <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
        <button class="button" type="submit">Analyser l’import Smart</button>
        <a class="button secondary" href="/tools">Retour Outils</a>
        <a class="button secondary" href="/tools/commander">Ouvrir PinCab Explorer</a>
      </div>
    </form>
  </div>

  <div class="card">
    <h2>Info Smart Import</h2>
    <table>
      <tr><td>Page</td><td><span class="ok">GET /tools/import-table</span></td></tr>
      <tr><td>Analyse</td><td><code>POST /tools/import-table/analyze</code></td></tr>
      <tr><td>Installation</td><td><code>POST /tools/import-table/install</code></td></tr>
      <tr><td>Dossier tables</td><td><code>/home/pinball/Tables</code></td></tr>
    </table>
  </div>
</div>
"""


def _tools_register_import_table_get_route(app):
    @app.route("/tools/import-table", methods=["GET"])
    def tools_import_table_get():
        if _TOOLS_PAGE_HELPER is not None:
            return _TOOLS_PAGE_HELPER("Outils", _tools_import_table_get_html())
        return _tools_import_table_get_html()

# ---------------------------------------------------------------------------
# Appearance page Phase C
# Dependencies:
# - Config: /opt/pincabos/config/webapp-appearance/active.json
# - Presets: /opt/pincabos/config/webapp-appearance/presets
# - Custom themes: /opt/pincabos/config/webapp-appearance/custom
# - Generated CSS: /opt/pincabos/web/static/pincabos-appearance-vars.css
# Created by Karots Sugarpie
# ---------------------------------------------------------------------------

def _tools_appearance_safe_json_load(path):
    try:
        p = Path(path)
        if p.exists() and p.is_file():
            return json.loads(p.read_text(errors="replace"))
    except Exception:
        return {}
    return {}


def _tools_appearance_theme_files():
    root = Path("/opt/pincabos/config/webapp-appearance")
    rows = []

    for kind, folder in (("preset", root / "presets"), ("custom", root / "custom")):
        try:
            if folder.exists():
                for item in sorted(folder.glob("*.json"), key=lambda x: x.name.lower()):
                    data = _tools_appearance_safe_json_load(item)
                    rows.append({
                        "kind": kind,
                        "name": data.get("name") or item.stem,
                        "path": str(item),
                        "description": data.get("description") or "",
                    })
        except Exception:
            pass

    return rows


def _tools_appearance_active_data():
    active_path = Path("/opt/pincabos/config/webapp-appearance/active.json")
    active = _tools_appearance_safe_json_load(active_path)
    theme = {}
    theme_file = active.get("active_file") or ""
    if theme_file:
        theme = _tools_appearance_safe_json_load(theme_file)

    return active, theme


def _tools_appearance_page_html():
    active, theme = _tools_appearance_active_data()
    rows = _tools_appearance_theme_files()
    tokens = theme.get("tokens", {}) if isinstance(theme, dict) else {}

    active_name = active.get("active_name") or theme.get("name") or "Inconnu"
    active_kind = active.get("active_kind") or theme.get("kind") or "unknown"
    active_file = active.get("active_file") or ""

    def token(name, fallback=""):
        return _tools_esc(tokens.get(name, fallback))

    theme_rows = []
    if rows:
        for row in rows:
            badge = "Actif" if row.get("path") == active_file else "Disponible"
            theme_rows.append(f"""
<tr>
  <td><strong>{_tools_esc(row.get("name"))}</strong><br><small>{_tools_esc(row.get("description"))}</small></td>
  <td>{_tools_esc(row.get("kind"))}</td>
  <td><code>{_tools_esc(row.get("path"))}</code></td>
  <td><span class="ok">{_tools_esc(badge)}</span></td>
</tr>
""")
    else:
        theme_rows.append("""
<tr>
  <td colspan="4"><span class="warn">Aucune apparence trouvée.</span></td>
</tr>
""")

    theme_select_options = []
    for row in rows:
        selected = " selected" if row.get("path") == active_file else ""
        label = f"{row.get('name')} [{row.get('kind')}]"
        theme_select_options.append(
            f'<option value="{_tools_esc(row.get("path"))}"{selected}>{_tools_esc(label)}</option>'
        )

    token_rows = []
    for key in sorted(tokens.keys()):
        token_rows.append(f"""
<tr>
  <td><code>{_tools_esc(key)}</code></td>
  <td><code>{_tools_esc(tokens.get(key))}</code></td>
</tr>
""")

    if not token_rows:
        token_rows.append("""
<tr><td colspan="2"><span class="warn">Aucun token trouvé.</span></td></tr>
""")

    status_messages = {
        "saved": "GO: nouvelle apparence personnalisée créée et appliquée.",
        "updated": "GO: apparence personnalisée mise à jour et appliquée.",
        "applied": "GO: apparence sélectionnée appliquée.",
        "classic": "GO: PinCabOS Classic restauré.",
        "duplicated": "GO: PinCabOS Classic dupliqué en apparence personnalisée.",
        "deleted": "GO: apparence personnalisée supprimée. PinCabOS Classic restauré.",
    }
    status_html = ""
    for flag, message in status_messages.items():
        if request.args.get(flag):
            status_html = f'<div class="card"><p class="ok">{_tools_esc(message)}</p></div>'
            break

    save_button_label = "Mettre à jour et appliquer" if active_kind == "custom" else "Créer et appliquer"
    save_help = (
        "Custom actif : les modifications mettront à jour cette apparence."
        if active_kind == "custom"
        else "Classic est actif : entre un nom pour créer une nouvelle apparence personnalisée."
    )

    return f"""
<h1>Apparence PinCabOS</h1>
{status_html}

<div class="card">
  <h2>Appliquer une apparence sauvegardée</h2>
  <p>
    Sélectionne une apparence existante, puis applique-la. Les paramètres du thème choisi
    deviennent les valeurs affichées dans le studio.
  </p>
  <form id="pcoAppearanceApplySavedForm" method="post" action="/tools/appearance/apply" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
    <select name="theme_path" required style="min-width:320px;max-width:100%;">
      {''.join(theme_select_options)}
    </select>
    <button class="button" type="submit">Appliquer la sélection</button>
  </form>
  <p class="warn" style="margin-top:10px;">
    PinCabOS Classic est protégé : il peut être appliqué ou restauré, mais jamais écrasé.
  </p>
</div>

<div class="card" id="pcoAppearanceD2EManagement">
  <h2>Gestion des apparences personnalisées</h2>
  <p>
    Duplique Classic pour créer rapidement une base modifiable, ou supprime le custom actif.
    Les presets et PinCabOS Classic sont protégés.
  </p>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
    <form method="post" action="/tools/appearance/duplicate-classic" style="display:inline;">
      <button class="button" type="submit">Dupliquer PinCabOS Classic</button>
    </form>
    <form method="post" action="/tools/appearance/delete-custom" style="display:inline;" onsubmit="return confirm('Supprimer cette apparence personnalisée active ?');">
      <input type="hidden" name="theme_path" value="{_tools_esc(active_file)}">
      <button class="button secondary" type="submit" {"disabled" if active_kind != "custom" else ""}>Supprimer le custom actif</button>
    </form>
  </div>
  <p class="warn" style="margin-top:10px;">
    Suppression disponible seulement quand une apparence custom est active.
  </p>
</div>


<style>
.pco-appearance-panel {{
  display: grid;
  grid-template-columns: minmax(320px, 1.15fr) minmax(320px, .85fr);
  gap: 18px;
  align-items: start;
}}
@media (max-width: 1100px) {{
  .pco-appearance-panel {{ grid-template-columns: 1fr; }}
}}
.pco-appearance-hero {{
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  flex-wrap: wrap;
}}
.pco-appearance-pill {{
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 176, 0, .35);
  background: rgba(0, 0, 0, .22);
  color: var(--pco-appearance-accent);
  font-weight: 700;
  white-space: nowrap;
}}
.pco-appearance-section {{
  margin-top: 16px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 122, 0, .22);
  background: rgba(0, 0, 0, .14);
}}
.pco-appearance-section h3 {{
  margin: 0 0 10px 0;
  color: var(--pco-appearance-accent);
}}
.pco-appearance-fields {{
  display: grid;
  grid-template-columns: repeat(2, minmax(210px, 1fr));
  gap: 12px;
}}
@media (max-width: 760px) {{
  .pco-appearance-fields {{ grid-template-columns: 1fr; }}
}}
.pco-appearance-field {{
  display: grid;
  gap: 6px;
  padding: 11px;
  border-radius: 14px;
  border: 1px solid rgba(255, 122, 0, .18);
  background: rgba(0, 0, 0, .16);
}}
.pco-appearance-field label {{
  font-weight: 700;
  color: var(--pco-appearance-muted-text);
}}
.pco-appearance-field small {{
  opacity: .82;
  line-height: 1.35;
}}
.pco-appearance-field input[type="color"] {{
  width: 72px;
  height: 42px;
  padding: 3px;
}}
.pco-appearance-field input[type="text"],
.pco-appearance-field input[type="range"] {{
  width: 100%;
}}
.pco-appearance-preview {{
  position: sticky;
  top: 14px;
}}
@media (max-width: 1100px) {{
  .pco-appearance-preview {{ position: static; }}
}}
.pco-appearance-preview-stage {{
  padding: 16px;
  border-radius: 18px;
  border: 1px dashed rgba(255, 176, 0, .38);
  background:
    radial-gradient(circle at top left, rgba(255, 122, 0, .15), transparent 34%),
    radial-gradient(circle at bottom right, rgba(95, 42, 145, .28), transparent 42%),
    rgba(0, 0, 0, .20);
}}
.pco-appearance-preview-card {{
  margin-top: 12px;
}}
.pco-appearance-actions {{
  margin-top: 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}}
.pco-appearance-disabled-note {{
  margin-top: 12px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 176, 0, .24);
  background: rgba(255, 176, 0, .08);
}}
.pco-appearance-mini-list {{
  display: grid;
  gap: 8px;
  margin: 10px 0 0 0;
  padding: 0;
  list-style: none;
}}
.pco-appearance-mini-list li {{
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(0, 0, 0, .18);
  border: 1px solid rgba(255, 122, 0, .14);
}}
</style>

<div class="card" id="pcoAppearanceD1Controls">
  <div class="pco-appearance-hero">
    <div>
      <h2>Studio Apparence PinCabOS</h2>
      <p>
        Ajuste les couleurs, bordures, rayons et ombres dans un aperçu local.
        En Phase D1, rien n’est sauvegardé et rien n’est appliqué au reste du site.
      </p>
    </div>
    <span class="pco-appearance-pill">Mode sécuritaire · Aperçu seulement</span>
  </div>

  <div class="pco-appearance-panel">
    <div>
      <div class="pco-appearance-section">
        <h3>1. Identité visuelle</h3>
        <div class="pco-appearance-fields">
          <div class="pco-appearance-field">
            <label>Accent principal</label>
            <input type="color" name="accent" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-accent" value="{token("accent", "#ffb000")}">
            <small>Titres, alertes et éléments importants.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Accent bouton / contour</label>
            <input type="color" name="accent2" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-accent2" value="{token("accent2", "#ff7a00")}">
            <small>Boutons, contours actifs et surbrillance.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Violet secondaire</label>
            <input type="color" name="purple" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-purple" value="{token("purple", "#5f2a91")}">
            <small>Boutons secondaires et ambiance PinCabOS.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Texte principal</label>
            <input type="color" name="page_text" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-page-text" value="{token("page_text", "#ffffff")}">
            <small>Couleur principale de lecture.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Texte secondaire</label>
            <input type="color" name="muted_text" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-muted-text" value="{token("muted_text", "#d8b8ff")}">
            <small>Descriptions, notes et textes d’aide.</small>
          </div>
        </div>
      </div>

      <div class="pco-appearance-section">
        <h3>2. Cartes et panneaux</h3>
        <div class="pco-appearance-fields">
          <div class="pco-appearance-field">
            <label>Fond des cartes</label>
            <input type="text" name="card_bg" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-card-bg" value="{token("card_bg", "rgba(29, 11, 46, 0.76)")}">
            <small>Accepte hex ou rgba. Exemple: <code>rgba(29, 11, 46, 0.76)</code></small>
          </div>
          <div class="pco-appearance-field">
            <label>Contour des cartes</label>
            <input type="color" name="card_border" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-card-border" value="{token("card_border", "#ff7a00")}">
            <small>Couleur du contour principal des cartes.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Rayon des cartes: <span id="pcoCardRadiusValue">{token("card_radius", "18px")}</span></label>
            <input type="range" min="0" max="36" step="1" name="card_radius" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-card-radius" data-pco-unit="px" value="{token("card_radius", "18px").replace("px", "")}">
            <small>0 = carré, 18 = look PinCabOS, 36 = très arrondi.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Ombre des cartes</label>
            <input type="text" name="card_shadow" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-card-shadow" value="{token("card_shadow", "0 0 25px rgba(255, 122, 0, 0.25)")}">
            <small>Exemple: <code>0 0 25px rgba(255, 122, 0, 0.25)</code></small>
          </div>
        </div>
      </div>

      <div class="pco-appearance-section">
        <h3>3. Boutons et champs</h3>
        <div class="pco-appearance-fields">
          <div class="pco-appearance-field">
            <label>Bouton principal</label>
            <input type="color" name="button_bg" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-button-bg" value="{token("button_bg", "#ff7a00")}">
            <small>Action principale dans les pages.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Texte bouton principal</label>
            <input type="color" name="button_text" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-button-text" value="{token("button_text", "#160020")}">
            <small>Texte affiché sur les boutons principaux.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Bouton secondaire</label>
            <input type="color" name="secondary_bg" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-secondary-bg" value="{token("secondary_bg", "#5f2a91")}">
            <small>Retour, options secondaires, navigation.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Rayon bouton: <span id="pcoButtonRadiusValue">{token("button_radius", "10px")}</span></label>
            <input type="range" min="0" max="30" step="1" name="button_radius" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-button-radius" data-pco-unit="px" value="{token("button_radius", "10px").replace("px", "")}">
            <small>Contrôle l’arrondi des boutons.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Fond des champs</label>
            <input type="color" name="input_bg" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-input-bg" value="{token("input_bg", "#050007")}">
            <small>Inputs, listes et zones de saisie.</small>
          </div>
          <div class="pco-appearance-field">
            <label>Contour des champs</label>
            <input type="color" name="input_border" form="pcoAppearanceSaveForm" data-pco-var="--pco-appearance-input-border" value="{token("input_border", "#ff7a00")}">
            <small>Bordure des champs de formulaire.</small>
          </div>
        </div>
      </div>
    </div>

    <div class="card pco-appearance-preview">
      <h2>Aperçu professionnel</h2>
      <p>Regarde le rendu avant d’enregistrer une apparence en Phase D2.</p>

      <div class="pco-appearance-preview-stage">
        <span class="pco-appearance-pill">Preview Cabinet</span>

        <div class="card pco-appearance-preview-card">
          <h2>Carte exemple</h2>
          <p>
            Cette carte utilise les variables actives que tu modifies localement.
            La disposition reste identique.
          </p>

          <p>
            <a class="button" href="#" onclick="return false;">Bouton principal</a>
            <a class="button secondary" href="#" onclick="return false;">Bouton secondaire</a>
          </p>

          <label>Champ exemple<br>
            <input type="text" value="PinCabOS WebApp" style="width:100%;">
          </label>

          <table>
            <tr><th>État</th><th>Résultat</th></tr>
            <tr><td>OK</td><td><span class="ok">Service actif</span></td></tr>
            <tr><td>WARN</td><td><span class="warn">À vérifier</span></td></tr>
            <tr><td>BAD</td><td><span class="bad">Erreur détectée</span></td></tr>
          </table>
        </div>
      </div>

      <div class="pco-appearance-actions">
        <button class="button" type="button" id="pcoAppearancePreviewReset">Restaurer aperçu</button>
        <form id="pcoAppearanceSaveForm" method="post" action="/tools/appearance/save-custom" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
          <input type="hidden" name="active_theme_path" value="{_tools_esc(active_file)}">
          <input type="text" name="theme_name" placeholder="Nom requis seulement pour créer depuis Classic" value="{'' if active_kind == 'preset' else _tools_esc(active_name)}" style="min-width:300px;">
          <button class="button secondary" type="submit">{_tools_esc(save_button_label)}</button>
          <small style="display:block;flex-basis:100%;opacity:.82;">{_tools_esc(save_help)}</small>
        </form>
        <form method="post" action="/tools/appearance/restore-classic" style="display:inline;">
          <button class="button secondary" type="submit">Restaurer PinCabOS Classic</button>
        </form>
      </div>

      <div class="pco-appearance-disabled-note">
        <strong>Phase D1 sécuritaire</strong><br>
        Phase D2H active : interface épurée, sélection par menu déroulant, gestion custom et protection des presets.
      </div>

      <ul class="pco-appearance-mini-list">
        <li>✅ Aperçu local immédiat</li>
        <li>✅ Aucune modification de layout</li>
        <li>✅ Routes POST Apparence sécurisées</li>
        <li>✅ Backup automatique avant écriture</li>
      </ul>
    </div>
  </div>
</div>

<script>
(function(){{
  var original = {{}};

  function setVar(name, value) {{
    if (!name) return;
    document.documentElement.style.setProperty(name, value);
  }}

  function currentInputValue(input) {{
    var value = input.value || "";
    var unit = input.getAttribute("data-pco-unit") || "";
    if (unit && value.indexOf(unit) === -1) {{
      value = value + unit;
    }}
    return value;
  }}

  function updateRadiusLabels(input, value) {{
    var cssVar = input.getAttribute("data-pco-var");
    if (cssVar === "--pco-appearance-card-radius") {{
      var el = document.getElementById("pcoCardRadiusValue");
      if (el) el.textContent = value;
    }}
    if (cssVar === "--pco-appearance-button-radius") {{
      var el2 = document.getElementById("pcoButtonRadiusValue");
      if (el2) el2.textContent = value;
    }}
  }}

  function applyInput(input) {{
    var cssVar = input.getAttribute("data-pco-var");
    var value = currentInputValue(input);
    setVar(cssVar, value);
    updateRadiusLabels(input, value);
  }}

  var inputs = document.querySelectorAll("#pcoAppearanceD1Controls [data-pco-var]");
  inputs.forEach(function(input) {{
    var cssVar = input.getAttribute("data-pco-var");
    original[cssVar] = currentInputValue(input);
    input.addEventListener("input", function() {{
      applyInput(input);
    }});
    input.addEventListener("change", function() {{
      applyInput(input);
    }});
  }});

  var reset = document.getElementById("pcoAppearancePreviewReset");
  if (reset) {{
    reset.addEventListener("click", function() {{
      inputs.forEach(function(input) {{
        var cssVar = input.getAttribute("data-pco-var");
        var value = original[cssVar] || "";
        var unit = input.getAttribute("data-pco-unit") || "";
        if (unit && value.endsWith(unit)) {{
          input.value = value.slice(0, -unit.length);
        }} else {{
          input.value = value;
        }}
        setVar(cssVar, value);
        updateRadiusLabels(input, value);
      }});
    }});
  }}
}})();
</script>




"""


def _tools_register_appearance_routes(app):
    @app.route("/tools/appearance", methods=["GET"])
    @app.route("/tools/apparence", methods=["GET"])
    def tools_appearance_page():
        if _TOOLS_PAGE_HELPER is not None:
            return _TOOLS_PAGE_HELPER("Outils", _tools_appearance_page_html())
        return _tools_appearance_page_html()

# ---------------------------------------------------------------------------
# Appearance Phase D2A write routes
# Dependencies:
# - Config root: /opt/pincabos/config/webapp-appearance
# - Generated CSS: /opt/pincabos/web/static/pincabos-appearance-vars.css
# - Backup root: /opt/pincabos/backups
# Created by Karots Sugarpie
# ---------------------------------------------------------------------------

_PCO_APPEARANCE_ROOT = Path("/opt/pincabos/config/webapp-appearance")
_PCO_APPEARANCE_PRESETS = _PCO_APPEARANCE_ROOT / "presets"
_PCO_APPEARANCE_CUSTOM = _PCO_APPEARANCE_ROOT / "custom"
_PCO_APPEARANCE_ACTIVE = _PCO_APPEARANCE_ROOT / "active.json"
_PCO_APPEARANCE_CLASSIC = _PCO_APPEARANCE_PRESETS / "PinCabOS Classic.json"
_PCO_APPEARANCE_CSS = Path("/opt/pincabos/web/static/pincabos-appearance-vars.css")


def _tools_appearance_backup_write_context():
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = Path("/opt/pincabos/backups") / f"webapp-appearance-write-{ts}"
    backup.mkdir(parents=True, exist_ok=True)

    if _PCO_APPEARANCE_ACTIVE.exists():
        shutil.copy2(_PCO_APPEARANCE_ACTIVE, backup / "active.json")
    if _PCO_APPEARANCE_CSS.exists():
        shutil.copy2(_PCO_APPEARANCE_CSS, backup / "pincabos-appearance-vars.css")
    if _PCO_APPEARANCE_ROOT.exists():
        shutil.copytree(_PCO_APPEARANCE_ROOT, backup / "webapp-appearance", dirs_exist_ok=True)

    return backup


def _tools_appearance_safe_theme_name(name):
    name = str(name or "").strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        raise ValueError("Nom d’apparence vide")
    if len(name) > 64:
        raise ValueError("Nom d’apparence trop long")
    if not re.match(r"^[A-Za-z0-9À-ÿ _.-]+$", name):
        raise ValueError("Nom d’apparence invalide")
    if name.lower() == "pincabos classic":
        raise ValueError("Le preset PinCabOS Classic ne peut pas être écrasé")
    return name


def _tools_appearance_safe_filename(name):
    safe = re.sub(r"[^A-Za-z0-9À-ÿ _.-]+", "-", name).strip(" .-")
    safe = safe[:64].strip()
    if not safe:
        safe = "Apparence PinCabOS"
    return safe + ".json"


def _tools_appearance_allowed_theme_path(path):
    p = Path(str(path or "")).expanduser()
    try:
        resolved = p.resolve()
        preset_root = _PCO_APPEARANCE_PRESETS.resolve()
        custom_root = _PCO_APPEARANCE_CUSTOM.resolve()
    except Exception:
        raise ValueError("Chemin invalide")

    if not resolved.exists() or not resolved.is_file() or resolved.suffix.lower() != ".json":
        raise ValueError("Fichier d’apparence absent ou invalide")

    if preset_root in resolved.parents or custom_root in resolved.parents:
        return resolved

    raise ValueError("Chemin d’apparence non autorisé")


def _tools_appearance_css_value_ok(value):
    value = str(value or "").strip()
    if not value:
        return False
    if any(x in value for x in [";", "{", "}", "<", ">"]):
        return False
    return True


def _tools_appearance_collect_tokens_from_form(base_tokens):
    allowed = {
        "accent", "accent2", "purple", "page_text", "muted_text",
        "card_bg", "card_border", "card_radius", "card_shadow",
        "button_bg", "button_text", "secondary_bg", "button_radius",
        "input_bg", "input_border",
    }

    tokens = dict(base_tokens or {})

    for key in allowed:
        if key not in request.form:
            continue
        value = str(request.form.get(key, "")).strip()

        if key in ("card_radius", "button_radius"):
            if re.fullmatch(r"[0-9]{1,2}", value):
                value = value + "px"

        if not _tools_appearance_css_value_ok(value):
            raise ValueError(f"Valeur CSS refusée pour {key}")

        tokens[key] = value

    return tokens


def _tools_appearance_load_active_theme():
    active = _tools_appearance_safe_json_load(_PCO_APPEARANCE_ACTIVE)
    theme_file = active.get("active_file") or str(_PCO_APPEARANCE_CLASSIC)
    theme_path = _tools_appearance_allowed_theme_path(theme_file)
    theme = _tools_appearance_safe_json_load(theme_path)
    return active, theme_path, theme


def _tools_appearance_write_active(theme_path, active_name, active_kind):
    data = {
        "schema": 1,
        "active_name": active_name,
        "active_kind": active_kind,
        "active_file": str(theme_path),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _PCO_APPEARANCE_ROOT.mkdir(parents=True, exist_ok=True)
    _PCO_APPEARANCE_ACTIVE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _tools_appearance_generate_css_from_theme(theme, theme_file):
    tokens = theme.get("tokens", {}) if isinstance(theme, dict) else {}

    def clean_key(key):
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(key)).strip("-").lower()

    safe = {}
    for key, value in tokens.items():
        k = clean_key(key)
        if not k:
            continue
        if not _tools_appearance_css_value_ok(value):
            raise ValueError(f"Valeur CSS refusée pour {k}")
        safe[k] = str(value).strip()

    def v(name, fallback):
        return safe.get(name, fallback)

    lines = [
        "/* PinCabOS Appearance Variables",
        f" * Generated from: {theme.get('name', 'unknown')}",
        f" * Source: {theme_file}",
        " * Created by Karots Sugarpie",
        " * Safe layer: visual variables only, no layout change.",
        " */",
        "",
        ":root {",
        f"  --pco-appearance-accent: {v('accent', '#ffb000')};",
        f"  --pco-appearance-accent2: {v('accent2', '#ff7a00')};",
        f"  --pco-appearance-purple: {v('purple', '#5f2a91')};",
        f"  --pco-appearance-page-text: {v('page_text', '#ffffff')};",
        f"  --pco-appearance-muted-text: {v('muted_text', '#d8b8ff')};",
        f"  --pco-appearance-card-bg: {v('card_bg', 'rgba(29, 11, 46, 0.76)')};",
        f"  --pco-appearance-card-border: {v('card_border', '#ff7a00')};",
        f"  --pco-appearance-card-radius: {v('card_radius', '18px')};",
        f"  --pco-appearance-card-shadow: {v('card_shadow', '0 0 25px rgba(255, 122, 0, 0.25)')};",
        f"  --pco-appearance-button-bg: {v('button_bg', '#ff7a00')};",
        f"  --pco-appearance-button-text: {v('button_text', '#160020')};",
        f"  --pco-appearance-button-radius: {v('button_radius', '10px')};",
        f"  --pco-appearance-secondary-bg: {v('secondary_bg', '#5f2a91')};",
        f"  --pco-appearance-secondary-text: {v('secondary_text', '#ffffff')};",
        f"  --pco-appearance-nav-active-bg: {v('nav_active_bg', '#ff7a00')};",
        f"  --pco-appearance-nav-active-text: {v('nav_active_text', '#160020')};",
        f"  --pco-appearance-nav-panel-bg: {v('nav_panel_bg', 'rgba(12, 0, 22, 0.58)')};",
        f"  --pco-appearance-nav-panel-border: {v('nav_panel_border', 'rgba(255, 122, 0, 0.25)')};",
        f"  --pco-appearance-input-bg: {v('input_bg', '#050007')};",
        f"  --pco-appearance-input-border: {v('input_border', '#ff7a00')};",
        f"  --pco-appearance-input-text: {v('input_text', '#eeeeee')};",
        f"  --pco-appearance-table-bg: {v('table_bg', '#050007')};",
        f"  --pco-appearance-ok: {v('ok', '#00ff99')};",
        f"  --pco-appearance-warn: {v('warn', '#ffb000')};",
        f"  --pco-appearance-bad: {v('bad', '#ff5555')};",
        "}",
        "",
        ".card {",
        "  background: var(--pco-appearance-card-bg) !important;",
        "  border-color: var(--pco-appearance-card-border) !important;",
        "  border-radius: var(--pco-appearance-card-radius) !important;",
        "  box-shadow: var(--pco-appearance-card-shadow) !important;",
        "}",
        ".card h2, h1, .nav-label { color: var(--pco-appearance-accent) !important; }",
        ".nav a, .button {",
        "  background: var(--pco-appearance-button-bg) !important;",
        "  color: var(--pco-appearance-button-text) !important;",
        "  border-radius: var(--pco-appearance-button-radius) !important;",
        "}",
        ".secondary {",
        "  background: var(--pco-appearance-secondary-bg) !important;",
        "  color: var(--pco-appearance-secondary-text) !important;",
        "  border-color: var(--pco-appearance-accent2) !important;",
        "}",
        ".nav a.active, .pincabos-nav a.active {",
        "  background: var(--pco-appearance-nav-active-bg) !important;",
        "  color: var(--pco-appearance-nav-active-text) !important;",
        "  border-color: var(--pco-appearance-accent) !important;",
        "}",
        ".nav-pages {",
        "  background: var(--pco-appearance-nav-panel-bg) !important;",
        "  border-color: var(--pco-appearance-nav-panel-border) !important;",
        "}",
        "input, select, textarea {",
        "  background: var(--pco-appearance-input-bg) !important;",
        "  color: var(--pco-appearance-input-text) !important;",
        "  border-color: var(--pco-appearance-input-border) !important;",
        "}",
        "table, pre { background: var(--pco-appearance-table-bg) !important; }",
        ".ok { color: var(--pco-appearance-ok) !important; }",
        ".warn { color: var(--pco-appearance-warn) !important; }",
        ".bad { color: var(--pco-appearance-bad) !important; }",
        "",
    ]

    _PCO_APPEARANCE_CSS.write_text("\n".join(lines))


def _tools_appearance_apply_theme_file(theme_path):
    theme_path = _tools_appearance_allowed_theme_path(theme_path)
    theme = _tools_appearance_safe_json_load(theme_path)
    name = theme.get("name") or theme_path.stem
    kind = theme.get("kind") or ("preset" if "presets" in str(theme_path) else "custom")

    _tools_appearance_backup_write_context()
    _tools_appearance_write_active(theme_path, name, kind)
    _tools_appearance_generate_css_from_theme(theme, theme_path)


def _tools_appearance_next_custom_copy_name(base_name):
    base = str(base_name or "PinCabOS Custom").strip() or "PinCabOS Custom"
    for idx in range(1, 1000):
        name = f"{base} Copie {idx}"
        path = _PCO_APPEARANCE_CUSTOM / _tools_appearance_safe_filename(name)
        if not path.exists():
            return name, path
    raise ValueError("Impossible de trouver un nom de copie disponible")


def _tools_appearance_duplicate_classic():
    classic = _tools_appearance_safe_json_load(_PCO_APPEARANCE_CLASSIC)
    tokens = classic.get("tokens", {}) if isinstance(classic, dict) else {}
    name, theme_path = _tools_appearance_next_custom_copy_name("PinCabOS Classic")

    data = {
        "schema": 1,
        "name": name,
        "kind": "custom",
        "description": "Copie personnalisable de PinCabOS Classic.",
        "created_by": "Karots Sugarpie",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tokens": tokens,
    }

    _PCO_APPEARANCE_CUSTOM.mkdir(parents=True, exist_ok=True)
    _tools_appearance_backup_write_context()
    theme_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _tools_appearance_write_active(theme_path, name, "custom")
    _tools_appearance_generate_css_from_theme(data, theme_path)
    return theme_path


def _tools_appearance_delete_custom(theme_path):
    target_path = _tools_appearance_allowed_theme_path(theme_path)
    target_resolved = target_path.resolve()
    custom_root = _PCO_APPEARANCE_CUSTOM.resolve()
    classic_resolved = _PCO_APPEARANCE_CLASSIC.resolve()

    if target_resolved == classic_resolved:
        raise ValueError("PinCabOS Classic ne peut pas être supprimé")
    if custom_root not in target_resolved.parents:
        raise ValueError("Seules les apparences personnalisées peuvent être supprimées")
    if not target_resolved.exists():
        raise ValueError("Apparence personnalisée introuvable")

    _tools_appearance_backup_write_context()
    target_resolved.unlink()

    active = _tools_appearance_safe_json_load(_PCO_APPEARANCE_ACTIVE)
    if str(target_resolved) == str(active.get("active_file") or ""):
        _tools_appearance_apply_theme_file(_PCO_APPEARANCE_CLASSIC)



def _tools_register_appearance_write_routes(app):
    @app.route("/tools/appearance/save-custom", methods=["POST"])
    def tools_appearance_save_custom():
        try:
            _active, active_theme_path, theme = _tools_appearance_load_active_theme()
            base_tokens = theme.get("tokens", {}) if isinstance(theme, dict) else {}
            tokens = _tools_appearance_collect_tokens_from_form(base_tokens)

            form_active_path = request.form.get("active_theme_path") or str(active_theme_path)
            target_path = _tools_appearance_allowed_theme_path(form_active_path)
            target_resolved = target_path.resolve()
            custom_root = _PCO_APPEARANCE_CUSTOM.resolve()
            classic_resolved = _PCO_APPEARANCE_CLASSIC.resolve()

            target_is_custom = custom_root in target_resolved.parents
            target_is_classic = target_resolved == classic_resolved

            # D2C:
            # - custom actif/sélectionné: mise à jour du même fichier
            # - Classic/preset: création d’un nouveau custom avec nom obligatoire
            if target_is_custom and not target_is_classic:
                existing = _tools_appearance_safe_json_load(target_path)
                provided_name = str(request.form.get("theme_name", "") or "").strip()

                if provided_name:
                    name = _tools_appearance_safe_theme_name(provided_name)
                else:
                    name = existing.get("name") or target_path.stem

                data = {
                    "schema": 1,
                    "name": name,
                    "kind": "custom",
                    "description": existing.get("description") or "Apparence personnalisée créée depuis la WebApp PinCabOS.",
                    "created_by": existing.get("created_by") or "Karots Sugarpie",
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "tokens": tokens,
                }

                _tools_appearance_backup_write_context()
                target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                _tools_appearance_write_active(target_path, name, "custom")
                _tools_appearance_generate_css_from_theme(data, target_path)

                return redirect("/tools/appearance?updated=1")

            name = _tools_appearance_safe_theme_name(request.form.get("theme_name"))
            _PCO_APPEARANCE_CUSTOM.mkdir(parents=True, exist_ok=True)
            theme_path = _PCO_APPEARANCE_CUSTOM / _tools_appearance_safe_filename(name)

            data = {
                "schema": 1,
                "name": name,
                "kind": "custom",
                "description": "Apparence personnalisée créée depuis la WebApp PinCabOS.",
                "created_by": "Karots Sugarpie",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tokens": tokens,
            }

            _tools_appearance_backup_write_context()
            theme_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            _tools_appearance_write_active(theme_path, name, "custom")
            _tools_appearance_generate_css_from_theme(data, theme_path)

            return redirect("/tools/appearance?saved=1")
        except Exception as exc:
            return _tools_wrap_page("Outils", f"<h1>Apparence PinCabOS</h1><div class='card'><h2>NOGOOD sauvegarde</h2><p class='bad'>{_tools_esc(exc)}</p><p><a class='button secondary' href='/tools/appearance'>Retour</a></p></div>"), 400

    @app.route("/tools/appearance/apply", methods=["POST"])
    def tools_appearance_apply():
        try:
            theme_path = request.form.get("theme_path")
            _tools_appearance_apply_theme_file(theme_path)
            return redirect("/tools/appearance?applied=1")
        except Exception as exc:
            return _tools_wrap_page("Outils", f"<h1>Apparence PinCabOS</h1><div class='card'><h2>NOGOOD application</h2><p class='bad'>{_tools_esc(exc)}</p><p><a class='button secondary' href='/tools/appearance'>Retour</a></p></div>"), 400

    @app.route("/tools/appearance/duplicate-classic", methods=["POST"])
    def tools_appearance_duplicate_classic_route():
        try:
            _tools_appearance_duplicate_classic()
            return redirect("/tools/appearance?duplicated=1")
        except Exception as exc:
            return _tools_wrap_page("Outils", f"<h1>Apparence PinCabOS</h1><div class='card'><h2>NOGOOD duplication</h2><p class='bad'>{_tools_esc(exc)}</p><p><a class='button secondary' href='/tools/appearance'>Retour</a></p></div>"), 400

    @app.route("/tools/appearance/delete-custom", methods=["POST"])
    def tools_appearance_delete_custom_route():
        try:
            theme_path = request.form.get("theme_path")
            _tools_appearance_delete_custom(theme_path)
            return redirect("/tools/appearance?deleted=1")
        except Exception as exc:
            return _tools_wrap_page("Outils", f"<h1>Apparence PinCabOS</h1><div class='card'><h2>NOGOOD suppression</h2><p class='bad'>{_tools_esc(exc)}</p><p><a class='button secondary' href='/tools/appearance'>Retour</a></p></div>"), 400

    @app.route("/tools/appearance/restore-classic", methods=["POST"])
    def tools_appearance_restore_classic():
        try:
            _tools_appearance_apply_theme_file(_PCO_APPEARANCE_CLASSIC)
            return redirect("/tools/appearance?classic=1")
        except Exception as exc:
            return _tools_wrap_page("Outils", f"<h1>Apparence PinCabOS</h1><div class='card'><h2>NOGOOD restauration</h2><p class='bad'>{_tools_esc(exc)}</p><p><a class='button secondary' href='/tools/appearance'>Retour</a></p></div>"), 400


# ---------------------------------------------------------------------------
# PinCabOS INI Full Editor override
# Added by PinCabOS patch: all VPinFE / VPinballX INI content editable.
# This intentionally overrides the earlier "safe editor" functions without
# deleting the old implementation, so rollback is simple from backup.
# ---------------------------------------------------------------------------

try:
    _TOOLS_ORIGINAL_INI_B2_PROFILES = _tools_ini_b2_profiles
except Exception:
    _TOOLS_ORIGINAL_INI_B2_PROFILES = None


def _tools_ini_b2_profiles():
    if callable(_TOOLS_ORIGINAL_INI_B2_PROFILES):
        profiles = _TOOLS_ORIGINAL_INI_B2_PROFILES()
    else:
        profiles = {}

    if "vpinfe" in profiles:
        profiles["vpinfe"]["subtitle"] = (
            "Full INI editor for VPinFE. All sections, comments, keys and values are editable. "
            "Automatic backup is created before saving."
        )

    if "vpx" in profiles:
        profiles["vpx"]["subtitle"] = (
            "Full INI editor for VPinballX.ini. All sections, comments, keys and values are editable. "
            "Automatic backup is created before saving."
        )

    return profiles


def _tools_ini_b2_save(profile_key):
    profiles = _tools_ini_b2_profiles()
    if profile_key not in profiles:
        raise ValueError("Unknown INI profile")

    profile = profiles[profile_key]
    path = Path(profile["path"])

    old_raw = path.read_text(errors="replace") if path.exists() else ""
    new_raw = request.form.get("ini_full_raw", "")

    # Normalize Windows/newline paste to Linux LF and keep exactly one final newline.
    new_raw = str(new_raw).replace("\r\n", "\n").replace("\r", "\n")
    new_raw = new_raw.rstrip("\n") + "\n"

    backup_dir = _tools_ini_b2_backup(path)

    if old_raw == new_raw:
        return backup_dir, []

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_raw, encoding="utf-8")

    try:
        os.chown(path, 1000, 1000)
    except Exception:
        pass

    return backup_dir, [("FULL", "RAW", "changed", "changed")]


def _tools_ini_page_html(title, subtitle, profile, ini_path):
    path = Path(ini_path)
    exists = path.exists()

    try:
        raw_text = path.read_text(errors="replace") if exists else ""
        read_error = ""
    except Exception as exc:
        raw_text = ""
        read_error = str(exc)

    profiles = _tools_ini_b2_profiles()
    edit_profile = profiles.get(profile, {})
    save_route = edit_profile.get("save_route", "")
    route = edit_profile.get("route", "")
    source_note = edit_profile.get("source_note", "")

    size_text = "absent"
    mtime_text = "absent"
    if exists:
        try:
            st = path.stat()
            size_text = f"{st.st_size:,} octets".replace(",", " ")
            mtime_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        except Exception:
            size_text = "lecture impossible"
            mtime_text = "lecture impossible"

    status_badge = "<span class='ok'>présent</span>" if exists else "<span class='bad'>absent</span>"
    if read_error:
        status_badge = "<span class='bad'>erreur lecture</span>"

    saved_html = ""
    if request.args.get("saved"):
        saved_html = "<div class='card'><p class='ok'>GO: INI saved with automatic backup.</p></div>"
    if request.args.get("nochange"):
        saved_html = "<div class='card'><p class='warn'>No change detected. INI left untouched except backup check.</p></div>"

    line_count = len(raw_text.splitlines())
    key_count = sum(1 for line in raw_text.splitlines() if "=" in line and not line.strip().startswith(("#", ";")))
    section_count = sum(1 for line in raw_text.splitlines() if line.strip().startswith("[") and line.strip().endswith("]"))

    body = f"""
<style>
  .pco-ini-full-layout {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }}
  .pco-ini-full-editor {{
    width: 100%;
    min-height: 72vh;
    height: 78vh;
    resize: vertical;
    box-sizing: border-box;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 13px;
    line-height: 1.35;
    white-space: pre;
    tab-size: 2;
  }}
  .pco-ini-kpis {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 12px 0;
  }}
  .pco-ini-kpi {{
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 12px;
    padding: 10px 12px;
    min-width: 120px;
    background: rgba(0,0,0,.14);
  }}
  .pco-ini-kpi strong {{
    display: block;
    font-size: 20px;
  }}
  .pco-ini-toolbar {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin: 12px 0;
  }}
</style>

<h1>{_tools_esc(title)}</h1>

{saved_html}

<div class="card">
  <h2>Full INI Editor</h2>
  <p>{_tools_esc(subtitle)}</p>
  <p>{_tools_esc(source_note)}</p>

  <table>
    <tr><td>Fichier</td><td><code>{_tools_esc(str(path))}</code></td></tr>
    <tr><td>Statut</td><td>{status_badge}</td></tr>
    <tr><td>Taille</td><td>{_tools_esc(size_text)}</td></tr>
    <tr><td>Modifié</td><td>{_tools_esc(mtime_text)}</td></tr>
  </table>

  <div class="pco-ini-kpis">
    <div class="pco-ini-kpi"><strong>{section_count}</strong><span>Sections</span></div>
    <div class="pco-ini-kpi"><strong>{key_count}</strong><span>Keys</span></div>
    <div class="pco-ini-kpi"><strong>{line_count}</strong><span>Lines</span></div>
    <div class="pco-ini-kpi"><strong>FULL</strong><span>Editable</span></div>
  </div>
</div>

<div class="card">
  <h2>Édition complète</h2>
  <p class="warn">
    Tout le contenu ci-dessous sera sauvegardé tel quel. Un backup automatique est créé avant chaque sauvegarde.
  </p>

  <form method="post" action="{_tools_esc(save_route)}">
    <textarea class="pco-ini-full-editor" name="ini_full_raw" spellcheck="false">{_tools_esc(raw_text)}</textarea>

    <div class="pco-ini-toolbar">
      <button class="button" type="submit" onclick="return confirm('Sauvegarder tout le fichier INI avec backup automatique ?');">
        Save full INI
      </button>
      <a class="button secondary" href="{_tools_esc(route)}">Reload</a>
      <a class="button secondary" href="/tools">Back to Tools</a>
    </div>
  </form>
</div>

<div class="card">
  <h2>Notes</h2>
  <ul>
    <li>Toutes les sections, clés, valeurs et commentaires sont modifiables.</li>
    <li>Tu peux ajouter une nouvelle section comme <code>[NouvelleSection]</code>.</li>
    <li>Tu peux ajouter une nouvelle clé comme <code>nouvellecle = valeur</code>.</li>
    <li>Si VPinFE ou VPX est ouvert, redémarre le service ou l’application après sauvegarde.</li>
  </ul>
</div>
"""

    if read_error:
        body = f"""
<h1>{_tools_esc(title)}</h1>
<div class="card">
  <h2 class="bad">Erreur lecture INI</h2>
  <p class="bad">{_tools_esc(read_error)}</p>
  <p><code>{_tools_esc(str(path))}</code></p>
  <p><a class="button secondary" href="/tools">Back</a></p>
</div>
"""

    return _tools_wrap_page("Outils", body)

# ---------------------------------------------------------------------------
# PinCabOS INI Full Excel Editor override
# Toutes les lignes INI sont affichées en tableau style Excel:
# Texte / clé, valeur défaut, champ éditable, description.
# ---------------------------------------------------------------------------

def _tools_ini_full_defaults(profile, section, key, value):
    defaults = {
        ("vpinfe", "Displays", "cabmode"): "true",
        ("vpinfe", "Displays", "tablescreenid"): "0",
        ("vpinfe", "Displays", "bgscreenid"): "",
        ("vpinfe", "Displays", "dmdscreenid"): "",
        ("vpinfe", "Displays", "fulldmdscreenid"): "2",
        ("vpinfe", "Displays", "tableorientation"): "landscape",
        ("vpinfe", "Displays", "tablerotation"): "0",
        ("vpinfe", "Settings", "vpxbinpath"): "/opt/pincabos/bin/vpx.sh",
        ("vpinfe", "Settings", "vpxinipath"): "/home/pinball/.vpinball/VPinballX.ini",
        ("vpinfe", "Settings", "tablerootdir"): "/home/pinball/Tables",
        ("vpinfe", "Settings", "muteaudio"): "false",
        ("vpinfe", "Settings", "manageruiport"): "8000",
        ("vpinfe", "Settings", "themeassetsport"): "8001",

        ("vpx", "Player", "FullScreen"): "1",
        ("vpx", "Player", "ShowFPS"): "0",
        ("vpx", "Player", "Exitconfirm"): "120",
        ("vpx", "Player", "DisableESC"): "0",
        ("vpx", "Displays", "cabmode"): "true",
        ("vpx", "Displays", "tablescreenid"): "0",
        ("vpx", "Displays", "bgscreenid"): "",
        ("vpx", "Displays", "dmdscreenid"): "",
        ("vpx", "Displays", "fulldmdscreenid"): "2",
        ("vpx", "Displays", "tableorientation"): "landscape",
        ("vpx", "Displays", "tablerotation"): "0",
    }

    exact = defaults.get((profile, section, key))
    if exact is not None:
        return exact

    exact_lower = defaults.get((profile, str(section), str(key).lower()))
    if exact_lower is not None:
        return exact_lower

    # Pour les clés inconnues, on affiche la valeur actuelle comme base de référence.
    return value



def _tools_ini_browse_button_html(field_name, current_value):
    safe_field = _tools_esc(str(field_name or ""))
    safe_path = _tools_esc(str(current_value or ""))
    return f"""
<div class="pco-ini-path-cell">
  <input class="pco-ini-path-input" type="text" name="{safe_field}" value="{safe_path}">
  <button class="button secondary pco-ini-browse-btn" type="button"
    onclick="window.open('/tools/ini/browse?target={safe_field}&path=' + encodeURIComponent(this.parentElement.querySelector('input').value || ''), 'pcoIniBrowse', 'width=980,height=760,scrollbars=yes,resizable=yes');">
    Parcourir
  </button>
</div>
"""

def _tools_ini_full_field(profile, section, key, value, idx):
    name = f"ini_value_{idx}"
    key_l = str(key or "").lower()
    val = str(value or "")

    def opt(v, label=None):
        label = v if label is None else label
        selected = " selected" if str(v) == val else ""
        return f'<option value="{_tools_esc(v)}"{selected}>{_tools_esc(label)}</option>'

    # Bool textuel.
    if val.lower() in {"true", "false"} or key_l in {
        "cabmode", "muteaudio", "enabledof", "console", "splashscreen",
        "autoupdatemediaonstartup", "disabledefaultchromeoptions",
        "mmhidequitbutton", "globaltableinioverrideenabled",
    }:
        values = ["true", "false"]
        if val.lower() not in values and val != "":
            values.append(val)
        return '<select name="' + _tools_esc(name) + '">' + "".join(opt(v) for v in values) + "</select>"

    # Bool VPX 0/1 seulement pour clés connues, pas pour toutes les touches clavier.
    if key_l in {
        "fullscreen", "showfps", "disableesc", "enabled", "windowed",
        "vsync", "syncmode", "useb2s", "usestereo", "forceexclusivefullscreen",
    }:
        values = ["0", "1"]
        if val not in values and val != "":
            values.append(val)
        return '<select name="' + _tools_esc(name) + '">' + "".join(opt(v) for v in values) + "</select>"

    # Orientation.
    if key_l in {"tableorientation", "orientation", "playfield_orientation"}:
        values = ["landscape", "portrait"]
        if val not in values and val != "":
            values.append(val)
        return '<select name="' + _tools_esc(name) + '">' + "".join(opt(v) for v in values) + "</select>"

    # Rotation.
    if key_l in {"tablerotation", "rotation", "playfield_rotation"}:
        values = ["0", "90", "180", "270"]
        if val not in values and val != "":
            values.append(val)
        return '<select name="' + _tools_esc(name) + '">' + "".join(opt(v) for v in values) + "</select>"

    # Screen ID.
    if "screenid" in key_l or key_l.endswith("_id") or key_l in {"screen_id", "tablescreenid", "bgscreenid", "dmdscreenid", "fulldmdscreenid"}:
        values = ["", "0", "1", "2", "3", "4", "5", "6", "7"]
        if val not in values:
            values.append(val)
        return '<select name="' + _tools_esc(name) + '">' + "".join(opt(v, "(empty)" if v == "" else v) for v in values) + "</select>"

    # Chemins longs: champ texte + bouton Parcourir filesystem PinCabOS.
    if "path" in key_l or "dir" in key_l or "folder" in key_l or "root" in key_l:
        return _tools_ini_browse_button_html(name, val)

    # Valeur standard.
    return f'<input type="text" name="{_tools_esc(name)}" value="{_tools_esc(val)}">'


def _tools_ini_page_html(title, subtitle, profile, ini_path):
    path = Path(ini_path)
    exists = path.exists()

    try:
        raw_lines = path.read_text(errors="replace").splitlines() if exists else []
        read_error = ""
    except Exception as exc:
        raw_lines = []
        read_error = str(exc)

    profiles = _tools_ini_b2_profiles()
    edit_profile = profiles.get(profile, {})
    save_route = edit_profile.get("save_route", "")
    route = edit_profile.get("route", "")
    source_note = edit_profile.get("source_note", "")

    rows = []
    current_section = "Sans section"
    idx = 0
    key_count = 0
    section_count = 0

    for raw in raw_lines:
        stripped = raw.strip()

        if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
            current_section = stripped[1:-1].strip()
            section_count += 1
            rows.append(f"""
<tr class="section-row">
  <td class="pco-ini-text" colspan="4">
    <input type="hidden" name="ini_type_{idx}" value="raw">
    <input type="text" name="ini_raw_{idx}" value="{_tools_esc(raw)}" class="pco-ini-section-input">
  </td>
</tr>
""")
            idx += 1
            continue

        if not stripped:
            rows.append(f"""
<tr class="blank-row">
  <td colspan="4">
    <input type="hidden" name="ini_type_{idx}" value="raw">
    <input type="hidden" name="ini_raw_{idx}" value="">
  </td>
</tr>
""")
            idx += 1
            continue

        if stripped.startswith("#") or stripped.startswith(";") or "=" not in raw:
            rows.append(f"""
<tr class="comment-row">
  <td class="pco-ini-text" colspan="4">
    <input type="hidden" name="ini_type_{idx}" value="raw">
    <input type="text" name="ini_raw_{idx}" value="{_tools_esc(raw)}" class="pco-ini-comment-input">
  </td>
</tr>
""")
            idx += 1
            continue

        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        key_count += 1

        default_value = _tools_ini_full_defaults(profile, current_section, key, value)
        desc = _tools_ini_description(profile, current_section, key)

        rows.append(f"""
<tr class="key-row">
  <td class="pco-ini-text">
    <input type="hidden" name="ini_type_{idx}" value="key">
    <input type="hidden" name="ini_section_{idx}" value="{_tools_esc(current_section)}">
    <input type="hidden" name="ini_key_{idx}" value="{_tools_esc(key)}">
    <strong>{_tools_esc(key)}</strong>
  </td>
  <td class="pco-ini-default"><code>{_tools_esc(default_value)}</code></td>
  <td class="pco-ini-edit">{_tools_ini_full_field(profile, current_section, key, value, idx)}</td>
  <td class="pco-ini-desc">{_tools_esc(desc)}</td>
</tr>
""")
        idx += 1

    status_badge = "<span class='ok'>présent</span>" if exists else "<span class='bad'>absent</span>"
    size_text = "absent"
    mtime_text = "absent"

    if exists:
        try:
            st = path.stat()
            size_text = f"{st.st_size:,} octets".replace(",", " ")
            mtime_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        except Exception:
            size_text = "lecture impossible"
            mtime_text = "lecture impossible"

    saved_html = ""
    if request.args.get("saved"):
        saved_html = "<div class='card'><p class='ok'>GO: INI saved with automatic backup.</p></div>"
    if request.args.get("nochange"):
        saved_html = "<div class='card'><p class='warn'>No change detected. INI left untouched except backup check.</p></div>"

    if read_error:
        return _tools_wrap_page("Outils", f"""
<h1>{_tools_esc(title)}</h1>
<div class="card">
  <h2 class="bad">Erreur lecture INI</h2>
  <p class="bad">{_tools_esc(read_error)}</p>
  <p><code>{_tools_esc(str(path))}</code></p>
  <p><a class="button secondary" href="/tools">Back</a></p>
</div>
""")

    table_rows = "".join(rows)

    body = f"""
<style>
  .pco-ini-excel-full-wrap {{
    overflow: auto;
    max-height: 78vh;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 14px;
  }}
  table.pco-ini-excel-full {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 16px;
  }}
  .pco-ini-excel-full th {{
    position: sticky;
    top: 0;
    z-index: 3;
    background: #2b0b3d;
    color: #fff;
    text-align: left;
    padding: 10px;
    border-bottom: 2px solid rgba(255,138,0,.8);
  }}
  .pco-ini-excel-full td {{
    padding: 8px 10px;
    border-bottom: 1px solid rgba(255,255,255,.08);
    vertical-align: top;
  }}
  .pco-ini-excel-full tr.key-row:nth-child(even) td {{
    background: rgba(255,255,255,.035);
  }}
  .pco-ini-excel-full tr.key-row:nth-child(odd) td {{
    background: rgba(255,138,0,.045);
  }}
  .pco-ini-excel-full tr.section-row td {{
    background: rgba(255,138,0,.22);
    border-top: 2px solid rgba(255,138,0,.55);
    border-bottom: 2px solid rgba(255,138,0,.35);
  }}
  .pco-ini-excel-full tr.comment-row td {{
    background: rgba(0,255,255,.045);
    color: rgba(255,255,255,.78);
  }}
  .pco-ini-excel-full input,
  .pco-ini-excel-full select,
  .pco-ini-excel-full textarea {{
    width: 100%;
    box-sizing: border-box;
    font-size: 16px;
    padding: 8px 9px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,.18);
    background: rgba(0,0,0,.22);
    color: #fff;
  }}
  .pco-ini-path-cell {{
    display: grid;
    grid-template-columns: minmax(260px, 1fr) auto;
    gap: 8px;
    align-items: center;
  }}
  .pco-ini-path-cell .pco-ini-path-input {{
    min-width: 260px;
  }}
  .pco-ini-browse-btn {{
    white-space: nowrap;
    padding: 8px 12px !important;
  }}

  .pco-ini-section-input {{
    font-weight: 900;
    color: #ffcc00 !important;
  }}
  .pco-ini-comment-input {{
    font-style: italic;
  }}
  .pco-ini-section-name {{
    color: #ffcc00;
    font-size: 14px;
    opacity: .9;
  }}
  .pco-ini-text {{
    min-width: 230px;
  }}
  .pco-ini-default {{
    min-width: 180px;
    max-width: 280px;
    overflow-wrap: anywhere;
  }}
  .pco-ini-edit {{
    min-width: 280px;
  }}
  .pco-ini-desc {{
    min-width: 320px;
    color: rgba(255,255,255,.86);
  }}
  .pco-ini-kpis {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin: 12px 0;
  }}
  .pco-ini-kpi {{
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 12px;
    padding: 10px 12px;
    min-width: 130px;
    background: rgba(0,0,0,.14);
  }}
  .pco-ini-kpi strong {{
    display: block;
    font-size: 20px;
  }}
  .pco-ini-toolbar {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 14px;
  }}
</style>

<h1>{_tools_esc(title)}</h1>

{saved_html}

<div class="card">
  <h2>Full Excel INI Editor</h2>
  <p>{_tools_esc(subtitle)}</p>
  <p>{_tools_esc(source_note)}</p>

  <table>
    <tr><td>Fichier</td><td><code>{_tools_esc(str(path))}</code></td></tr>
    <tr><td>Statut</td><td>{status_badge}</td></tr>
    <tr><td>Taille</td><td>{_tools_esc(size_text)}</td></tr>
    <tr><td>Modifié</td><td>{_tools_esc(mtime_text)}</td></tr>
  </table>

  <div class="pco-ini-kpis">
    <div class="pco-ini-kpi"><strong>{section_count}</strong><span>Sections</span></div>
    <div class="pco-ini-kpi"><strong>{key_count}</strong><span>Keys</span></div>
    <div class="pco-ini-kpi"><strong>{idx}</strong><span>Lignes</span></div>
    <div class="pco-ini-kpi"><strong>FULL</strong><span>Editable</span></div>
  </div>
</div>

<form method="post" action="{_tools_esc(save_route)}">
  <input type="hidden" name="ini_excel_mode" value="1">
  <input type="hidden" name="ini_row_count" value="{idx}">

  <div class="card">
    <h2>Tableau INI style Excel</h2>
    <p class="warn">
      Chaque clé est éditable. Les sections et commentaires sont aussi modifiables.
      Backup automatique avant sauvegarde.
    </p>

    <div class="pco-ini-excel-full-wrap">
      <table class="pco-ini-excel-full">
        <thead>
          <tr>
            <th>Texte / clé</th>
            <th>Valeur par défaut</th>
            <th>Champ éditable</th>
            <th>Description de la fonction</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>

    <div class="pco-ini-toolbar">
      <button class="button" type="submit" onclick="return confirm('Sauvegarder le INI complet avec backup automatique ?');">
        Save full Excel INI
      </button>
      <a class="button secondary" href="{_tools_esc(route)}">Reload</a>
      <a class="button secondary" href="/tools">Back to Tools</a>
    </div>
  </div>
</form>
"""

    return _tools_wrap_page("Outils", body)


def _tools_ini_b2_save(profile_key):
    profiles = _tools_ini_b2_profiles()
    if profile_key not in profiles:
        raise ValueError("Unknown INI profile")

    profile = profiles[profile_key]
    path = Path(profile["path"])

    old_raw = path.read_text(errors="replace") if path.exists() else ""
    backup_dir = _tools_ini_b2_backup(path)

    # Nouveau mode tableau Excel.
    if request.form.get("ini_excel_mode") == "1":
        try:
            count = int(request.form.get("ini_row_count", "0"))
        except Exception:
            count = 0

        out = []
        for idx in range(count):
            typ = request.form.get(f"ini_type_{idx}", "")

            if typ == "raw":
                out.append(str(request.form.get(f"ini_raw_{idx}", "")).rstrip("\n"))
                continue

            if typ == "key":
                key = str(request.form.get(f"ini_key_{idx}", "")).strip()
                value = str(request.form.get(f"ini_value_{idx}", "")).replace("\r\n", "\n").replace("\r", "\n")
                value = value.split("\n")[0]
                if key:
                    out.append(f"{key} = {value}")
                continue

        new_raw = "\n".join(out).rstrip("\n") + "\n"

        if old_raw == new_raw:
            return backup_dir, []

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_raw, encoding="utf-8")

        try:
            os.chown(path, 1000, 1000)
        except Exception:
            pass

        return backup_dir, [("FULL", "EXCEL", "changed", "changed")]

    # Fallback ancien mode si vieux formulaire.
    lines = old_raw.splitlines() if old_raw else []
    changed = []
    for meta in profile.get("keys", []):
        field = f"ini__{meta['section']}__{meta['key']}"
        if field not in request.form:
            continue
        new_value = _tools_ini_b2_validate_value(meta, request.form.get(field, ""))
        old_value = _tools_ini_b2_read_value(lines, meta["section"], meta["key"])
        if old_value != new_value:
            lines = _tools_ini_b2_set_key(lines, meta["section"], meta["key"], new_value)
            changed.append((meta["section"], meta["key"], old_value, new_value))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        os.chown(path, 1000, 1000)
    except Exception:
        pass

    return backup_dir, changed

# ---------------------------------------------------------------------------
# PinCabOS INI GitHub description override
# Sources:
# - VPinFE GitHub technical_details.md: vpinfe.ini definition.
# - VPinFE GitHub README: libdmdutil configuration.
# - vpinball/vpinball GitHub release notes: VPinballX.ini stores VPX settings,
#   supports standalone platforms and contains hundreds of settings.
# ---------------------------------------------------------------------------

def _tools_ini_description(profile, section, key):
    s = str(section or "").strip()
    k = str(key or "").strip()
    sl = s.lower()
    kl = k.lower()

    # Exact VPinFE descriptions documented in upstream GitHub technical_details.md.
    vpinfe_exact = {
        ("displays", "bgscreenid"): "VPinFE GitHub: Backglass screen number. Use --listres to list monitor IDs. Leave blank when no backglass display is assigned.",
        ("displays", "dmdscreenid"): "VPinFE GitHub: DMD screen number. Use --listres to list monitor IDs. Leave blank when no DMD display is assigned.",
        ("displays", "tablescreenid"): "VPinFE GitHub: Table/playfield screen number. Use --listres to list monitor IDs. Leave blank only when no table display is assigned.",

        ("settings", "vpxbinpath"): "VPinFE GitHub: Full path to the VPX binary or launcher used to start Visual Pinball.",
        ("settings", "tablerootdir"): "VPinFE GitHub: Root folder where all VPX table folders/files are located.",
        ("settings", "startup_collection"): "VPinFE GitHub: Collection name VPinFE opens on startup. It is case-sensitive and must match the collection name.",
        ("settings", "splashscreen"): "VPinFE GitHub: Enables or disables the splash screen during startup. Default is false.",

        ("input", "joyleft"): "VPinFE GitHub: Gamepad button ID used to move left. IDs come from --gamepadtest.",
        ("input", "joyright"): "VPinFE GitHub: Gamepad button ID used to move right. IDs come from --gamepadtest.",
        ("input", "joyup"): "VPinFE GitHub: Gamepad button ID used to move up. IDs come from --gamepadtest.",
        ("input", "joydown"): "VPinFE GitHub: Gamepad button ID used to move down. IDs come from --gamepadtest.",
        ("input", "joyselect"): "VPinFE GitHub: Gamepad button ID for Select / Launch. IDs come from --gamepadtest.",
        ("input", "joymenu"): "VPinFE GitHub: Gamepad button ID for the pop-up menu. IDs come from --gamepadtest.",
        ("input", "joyback"): "VPinFE GitHub: Gamepad button ID for Go Back. IDs come from --gamepadtest.",
        ("input", "joytutorial"): "VPinFE GitHub: Gamepad button ID to open the Pinball Primer tutorial overlay. IDs come from --gamepadtest.",
        ("input", "joyexit"): "VPinFE GitHub: Gamepad button ID to exit VPinFE. IDs come from --gamepadtest.",
        ("input", "joycollectionmenu"): "VPinFE GitHub: Gamepad button ID to open the collection menu in the Theme UI. IDs come from --gamepadtest.",

        ("libdmdutil", "enabled"): "VPinFE GitHub README: Enables VPinFE libdmdutil support. When true, VPinFE loads the bundled libdmdutil wrapper.",
        ("libdmdutil", "pin2dmdenabled"): "VPinFE GitHub README: Preserved libdmdutil-related Pin2DMD option in vpinfe.ini.",
        ("libdmdutil", "pixelcadedevice"): "VPinFE GitHub README: Preserved libdmdutil-related Pixelcade device field.",
        ("libdmdutil", "zedmddevice"): "VPinFE GitHub README: ZeDMD device path. If set, VPinFE connects to this device path first.",
        ("libdmdutil", "zedmdwifiaddr"): "VPinFE GitHub README: ZeDMD Wi-Fi address. Used when zedmddevice is blank.",
    }

    if profile == "vpinfe":
        desc = vpinfe_exact.get((sl, kl))
        if desc:
            return desc

        # VPinFE / PinCabOS local extensions.
        if kl == "vpxinipath":
            return "PinCabOS/VPinFE: Path to the active VPinballX.ini file used by the VPX launcher and frontend integration."
        if kl == "vpxlaunchenv":
            return "VPinFE launch setting: Extra environment variables or launch environment override for starting VPX."
        if kl == "globalinioverride":
            return "VPinFE launch setting: Global INI override path/value used when launching tables, if configured."
        if kl == "globaltableinioverrideenabled":
            return "VPinFE launch setting: Enables a global per-table INI override workflow."
        if kl == "globaltableinioverridemask":
            return "VPinFE launch setting: Filename mask/pattern used for global table INI overrides."
        if kl == "vpxlogdeleteonstart":
            return "VPinFE launch setting: Deletes/cleans the VPX log at startup when enabled."
        if kl == "theme":
            return "VPinFE setting: Active frontend theme name loaded by the Theme UI."
        if kl == "autoupdatemediaonstartup":
            return "VPinFE media setting: Automatically updates table media at startup when enabled."
        if kl == "muteaudio":
            return "VPinFE audio setting: Mutes frontend UI audio when enabled."
        if kl == "chromeoptions":
            return "VPinFE UI setting: Extra Chromium/Chrome options used by the frontend UI."
        if kl == "disabledefaultchromeoptions":
            return "VPinFE UI setting: Disables VPinFE default Chromium options when enabled."
        if kl == "mmhidequitbutton":
            return "VPinFE Manager/UI setting: Hides the quit button in manager/menu UI when enabled."
        if kl in {"themeassetsport", "manageruiport"}:
            return "VPinFE GitHub README: Local web service port used by VPinFE server listeners / management UI."
        if sl == "logger" and kl == "level":
            return "VPinFE logging setting: Log verbosity level, for example debug/info/warning/error."
        if sl == "logger" and kl == "console":
            return "VPinFE logging setting: Enables console logging output when true."
        if sl == "dof" and kl == "enabledof":
            return "VPinFE DOF setting: Enables DirectOutput Framework integration when available."
        if sl == "dof" and kl == "dofconfigtoolapikey":
            return "VPinFE DOF setting: API key used for DOF Config Tool integration, when configured."
        if sl.startswith("pincabos"):
            return "PinCabOS extension: Local PinCabOS integration value used by the WebApp, screen tools, VPX launcher or cabinet helpers."

        return "VPinFE setting: not fully documented upstream; editable local vpinfe.ini value detected from the active configuration."

    # VPX / VPinballX descriptions.
    # Official vpinball GitHub release notes confirm VPinballX.ini stores settings, allows
    # easier manual/third-party editing, table overrides, and sharing across standalone platforms.
    vpx_exact = {
        ("player", "fullscreen"): "VPinballX setting: Runs VPX in fullscreen mode. Important for cabinet/playfield display.",
        ("player", "showfps"): "VPinballX setting: Shows the FPS counter for performance debugging.",
        ("player", "exitconfirm"): "VPinballX setting: Controls exit confirmation behavior before closing a table.",
        ("player", "disableesc"): "VPinballX setting: Controls whether ESC is disabled/ignored for cabinet workflows.",
        ("player", "pbwdefaultlayout"): "VPinballX setting: Default layout selection for plunger/Pinball Wizard style input.",
        ("player", "debugballs"): "VPinballX setting: Debug key binding used for ball/debug behavior.",
        ("player", "debugger"): "VPinballX setting: Key binding used to open or trigger debugger behavior.",
        ("player", "framecount"): "VPinballX setting: Key binding used to toggle frame/performance counter behavior.",
        ("player", "addcreditkey"): "VPinballX setting: Keyboard mapping for adding a credit.",
        ("player", "addcreditkey2"): "VPinballX setting: Secondary keyboard mapping for adding a credit.",
        ("player", "startgamekey"): "VPinballX setting: Keyboard mapping for Start Game.",
        ("player", "exitgamekey"): "VPinballX setting: Keyboard mapping for Exit Game.",
        ("player", "pausekey"): "VPinballX setting: Keyboard mapping for Pause.",
        ("player", "escapekey"): "VPinballX setting: Keyboard mapping for Escape.",
        ("player", "volumeup"): "VPinballX setting: Keyboard mapping for Volume Up.",
        ("player", "volumedown"): "VPinballX setting: Keyboard mapping for Volume Down.",

        ("displays", "cabmode"): "VPinballX cabinet display setting: Enables cabinet-oriented display behavior.",
        ("displays", "tablescreenid"): "VPinballX cabinet display setting: Screen ID used for the playfield/table display.",
        ("displays", "bgscreenid"): "VPinballX cabinet display setting: Screen ID used for backglass output when assigned.",
        ("displays", "dmdscreenid"): "VPinballX cabinet display setting: Screen ID used for DMD output when assigned.",
        ("displays", "fulldmdscreenid"): "VPinballX cabinet display setting: Screen ID used for FullDMD output on a 3-screen cabinet.",
        ("displays", "tableorientation"): "VPinballX/PinCabOS display setting: Playfield orientation label, commonly landscape or portrait.",
        ("displays", "tablerotation"): "VPinballX/PinCabOS display setting: Playfield rotation in degrees, commonly 0, 90, 180 or 270.",
    }

    desc = vpx_exact.get((sl, kl))
    if desc:
        return desc

    # Pattern-based VPX descriptions for the many keys in VPinballX.ini.
    if kl.startswith("joy"):
        return "VPinballX input setting: Joystick/gamepad button mapping for this function."
    if kl.endswith("key") or "key" in kl:
        return "VPinballX input setting: Keyboard scan-code mapping for this gameplay/control function."
    if kl in {"lflipkey", "rflipkey", "stagedlflipkey", "stagedrflipkey"}:
        return "VPinballX input setting: Flipper keyboard mapping."
    if "tilt" in kl:
        return "VPinballX input setting: Tilt/nudge related control mapping or behavior."
    if "plunger" in kl:
        return "VPinballX input setting: Plunger control mapping or plunger behavior."
    if "magnasave" in kl:
        return "VPinballX input setting: MagnaSave button mapping."
    if "sound" in sl or "audio" in sl or "volume" in kl or "music" in kl:
        return "VPinballX audio setting: Controls sound device, volume, music or audio output behavior."
    if "bgfx" in sl or "renderer" in kl or "graphics" in sl or "video" in sl:
        return "VPinballX rendering setting: Controls graphics, renderer, BGFX/OpenGL/DirectX-style rendering or display behavior."
    if "dmd" in sl or "dmd" in kl:
        return "VPinballX display setting: Controls DMD, FullDMD or external DMD display behavior."
    if "b2s" in kl or "backglass" in kl or "bg" == kl[:2]:
        return "VPinballX backglass setting: Controls backglass/B2S related output or behavior."
    if "pinmame" in kl or "rom" in kl:
        return "VPinballX/PinMAME setting: Controls ROM/PinMAME integration path or behavior."
    if "path" in kl or "dir" in kl or "folder" in kl:
        return "VPinballX path setting: Filesystem path used by VPX or a related cabinet component."
    if "width" in kl or "height" in kl or kl in {"x", "y"} or kl.endswith("x") or kl.endswith("y"):
        return "VPinballX geometry setting: Position or size value used for a window, DMD, display or cabinet component."
    if "log" in kl:
        return "VPinballX logging setting: Controls log output or log handling."
    if "debug" in kl:
        return "VPinballX debug setting: Controls debugging, diagnostics or developer behavior."
    if "fps" in kl:
        return "VPinballX performance display setting: Controls FPS/performance counter behavior."

    return "VPinballX.ini setting: official VPX settings file value. The vpinball GitHub release notes describe this INI as the editable settings store for VPX and standalone platforms."


# ---------------------------------------------------------------------------
# PinCabOS INI browser route override
# Adds /tools/ini/browse and preserves the original INI routes.
# ---------------------------------------------------------------------------

_TOOLS_REGISTER_INI_READONLY_ROUTES_ORIG = _tools_register_ini_readonly_routes

def _tools_register_ini_readonly_routes__with_browser(app):
    _TOOLS_REGISTER_INI_READONLY_ROUTES_ORIG(app)

    @app.route("/tools/ini/browse")
    def tools_ini_browse():
        target = request.args.get("target", "")
        requested = request.args.get("path", "") or "/home/pinball"

        try:
            base = Path(requested).expanduser()
            if base.is_file():
                base = base.parent
            if not base.exists():
                base = Path("/home/pinball")
            base = base.resolve()
        except Exception:
            base = Path("/home/pinball")

        quick_roots = [
            Path("/home/pinball"),
            Path("/home/pinball/.vpinball"),
            Path("/home/pinball/Tables"),
            Path("/opt/pincabos"),
            Path("/opt/pincabos/bin"),
            Path("/opt/pincabos/apps"),
            Path("/opt/pincabos/config"),
            Path("/mnt"),
            Path("/media"),
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/"),
        ]

        rows = []
        parent = base.parent if base != base.parent else base

        rows.append(f"""
<tr>
  <td>📁</td>
  <td><a href="/tools/ini/browse?target={_tools_esc(target)}&path={_tools_esc(str(parent))}">..</a></td>
  <td>Dossier parent</td>
  <td></td>
</tr>
""")

        try:
            items = sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception as exc:
            items = []
            rows.append(f"<tr><td colspan='4' class='bad'>Erreur lecture: {_tools_esc(exc)}</td></tr>")

        for item in items[:500]:
            try:
                is_dir = item.is_dir()
                icon = "📁" if is_dir else "📄"
                kind = "Dossier" if is_dir else "Fichier"
                path_txt = str(item)
                safe_path = _tools_esc(path_txt)

                open_link = ""
                if is_dir:
                    open_link = (
                        '<a class="button secondary" href="/tools/ini/browse?target='
                        + _tools_esc(target)
                        + '&path='
                        + safe_path
                        + '">Ouvrir</a>'
                    )

                choose_btn = (
                    '<button class="button" type="button" data-path="'
                    + safe_path
                    + '" onclick="choosePath(this.dataset.path)">Choisir</button>'
                )

                rows.append(f"""
<tr>
  <td>{icon}</td>
  <td><code>{_tools_esc(item.name)}</code></td>
  <td>{kind}</td>
  <td style="display:flex;gap:8px;flex-wrap:wrap;">{open_link}{choose_btn}</td>
</tr>
""")
            except Exception:
                continue

        quick = "".join(
            '<a class="button secondary" href="/tools/ini/browse?target='
            + _tools_esc(target)
            + '&path='
            + _tools_esc(str(q))
            + '">'
            + _tools_esc(str(q))
            + '</a> '
            for q in quick_roots
            if q.exists()
        )

        body = f"""
<style>
  .pco-browser-toolbar {{
    display:flex;
    gap:8px;
    flex-wrap:wrap;
    margin:10px 0 14px 0;
  }}
  .pco-browser-table {{
    width:100%;
    border-collapse:separate;
    border-spacing:0;
  }}
  .pco-browser-table th {{
    position:sticky;
    top:0;
    background:#2b0b3d;
    color:#fff;
    padding:10px;
    text-align:left;
    border-bottom:2px solid rgba(255,138,0,.75);
  }}
  .pco-browser-table td {{
    padding:8px 10px;
    border-bottom:1px solid rgba(255,255,255,.08);
  }}
  .pco-browser-table tr:nth-child(even) td {{
    background:rgba(255,255,255,.035);
  }}
  .pco-browser-table tr:nth-child(odd) td {{
    background:rgba(255,138,0,.045);
  }}
</style>

<h1>Parcourir le système</h1>

<div class="card">
  <h2>Chemin courant</h2>
  <p><code>{_tools_esc(str(base))}</code></p>
  <p>Champ cible: <code>{_tools_esc(target)}</code></p>
  <div class="pco-browser-toolbar">
    {quick}
  </div>
</div>

<div class="card">
  <h2>Fichiers / dossiers</h2>
  <div class="pco-browser-table-wrap">
  <table class="pco-browser-table">
    <thead>
      <tr>
        <th></th>
        <th>Nom</th>
        <th>Type</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  </div>
</div>

<script>
function choosePath(p) {{
  try {{
    if (window.opener && !window.opener.closed) {{
      var target = "{_tools_esc(target)}";
      var el = window.opener.document.querySelector('[name="' + CSS.escape(target) + '"]');
      if (el) {{
        el.value = p;
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        window.close();
        return;
      }}
    }}
  }} catch(e) {{}}
  alert("Chemin choisi: " + p);
}}
</script>
"""
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Parcourir le système - PinCabOS</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #120019;
      --card: #21102f;
      --line: rgba(255,255,255,.12);
      --text: #ffffff;
      --muted: rgba(255,255,255,.72);
      --accent: #ff8a00;
      --accent2: #ffcc00;
    }}
    body {{
      margin: 0;
      padding: 16px;
      background: radial-gradient(circle at top left, #3b1151 0, var(--bg) 46%, #07000b 100%);
      color: var(--text);
      font-family: system-ui, -apple-system, Segoe UI, sans-serif;
      font-size: 15px;
    }}
    h1 {{
      margin: 0 0 12px 0;
      font-size: 24px;
    }}
    h2 {{
      margin: 0 0 10px 0;
      font-size: 18px;
      color: var(--accent2);
    }}
    .card {{
      background: rgba(33,16,47,.94);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,.25);
    }}
    code {{
      color: #fff;
      background: rgba(0,0,0,.28);
      border: 1px solid rgba(255,255,255,.08);
      padding: 2px 5px;
      border-radius: 6px;
      word-break: break-all;
    }}
    .button {{
      display: inline-block;
      appearance: none;
      border: 0;
      border-radius: 10px;
      background: var(--accent);
      color: #000;
      font-weight: 800;
      padding: 8px 12px;
      text-decoration: none;
      cursor: pointer;
      font-size: 14px;
    }}
    .button.secondary {{
      background: rgba(255,255,255,.11);
      color: #fff;
      border: 1px solid rgba(255,255,255,.16);
    }}
    .pco-browser-toolbar {{
      display:flex;
      gap:8px;
      flex-wrap:wrap;
      margin:10px 0 0 0;
    }}
    .pco-browser-table-wrap {{
      max-height: 68vh;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 12px;
    }}
    .pco-browser-table {{
      width:100%;
      border-collapse:separate;
      border-spacing:0;
    }}
    .pco-browser-table th {{
      position:sticky;
      top:0;
      background:#2b0b3d;
      color:#fff;
      padding:10px;
      text-align:left;
      border-bottom:2px solid rgba(255,138,0,.75);
      z-index: 2;
    }}
    .pco-browser-table td {{
      padding:8px 10px;
      border-bottom:1px solid rgba(255,255,255,.08);
      vertical-align: middle;
    }}
    .pco-browser-table tr:nth-child(even) td {{
      background:rgba(255,255,255,.035);
    }}
    .pco-browser-table tr:nth-child(odd) td {{
      background:rgba(255,138,0,.045);
    }}
    .topbar {{
      display:flex;
      justify-content:space-between;
      align-items:center;
      gap:12px;
      margin-bottom:12px;
    }}
    .muted {{
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <div class="topbar">
    <h1>Parcourir le système</h1>
    <button class="button secondary" type="button" onclick="window.close()">Fermer</button>
  </div>
  {body}
</body>
</html>"""

_tools_register_ini_readonly_routes = _tools_register_ini_readonly_routes__with_browser

# ---------------------------------------------------------------------------
# PinCabOS INI save hardguard
# The Excel UI may display sections/descriptions/help text, but saving must only
# update existing key=value lines from the original INI. It must not add UI text,
# descriptions, new sections, comments, or extra lines into the INI.
# ---------------------------------------------------------------------------

def _tools_ini_b2_save(profile_key):
    profiles = _tools_ini_b2_profiles()
    if profile_key not in profiles:
        raise ValueError("Unknown INI profile")

    profile = profiles[profile_key]
    path = Path(profile["path"])

    old_raw = path.read_text(errors="replace") if path.exists() else ""
    old_lines = old_raw.splitlines()
    backup_dir = _tools_ini_b2_backup(path)

    # Excel mode: update existing key=value rows only.
    if request.form.get("ini_excel_mode") == "1":
        try:
            count = int(request.form.get("ini_row_count", "0"))
        except Exception:
            count = 0

        # Build submitted values by row order. The rendered page creates one key row per
        # original key=value line, so row identity is section+key+index.
        submitted = []
        for idx in range(count):
            typ = request.form.get(f"ini_type_{idx}", "")
            if typ != "key":
                continue

            sec = str(request.form.get(f"ini_section_{idx}", "")).strip()
            key = str(request.form.get(f"ini_key_{idx}", "")).strip()
            val = str(request.form.get(f"ini_value_{idx}", ""))
            val = val.replace("\r\n", "\n").replace("\r", "\n").split("\n")[0]

            if key:
                submitted.append({
                    "section": sec,
                    "key": key,
                    "value": val,
                    "used": False,
                })

        current_section = "Sans section"
        new_lines = []
        changed = []

        for line in old_lines:
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
                current_section = stripped[1:-1].strip()
                new_lines.append(line)
                continue

            if not stripped or stripped.startswith("#") or stripped.startswith(";") or "=" not in line:
                new_lines.append(line)
                continue

            old_key_raw, old_value_raw = line.split("=", 1)
            old_key = old_key_raw.strip()
            old_value = old_value_raw.strip()

            replacement = None
            for item in submitted:
                if item["used"]:
                    continue
                if item["section"].lower() == current_section.lower() and item["key"].lower() == old_key.lower():
                    replacement = item
                    item["used"] = True
                    break

            if replacement is None:
                new_lines.append(line)
                continue

            new_value = replacement["value"]

            if old_value != new_value:
                changed.append((current_section, old_key, old_value, new_value))

            # Preserve original key spacing style as much as possible.
            if "=" in line:
                prefix = old_key_raw.rstrip()
                if " = " in line:
                    new_lines.append(f"{prefix} = {new_value}")
                else:
                    new_lines.append(f"{prefix}={new_value}")
            else:
                new_lines.append(f"{old_key} = {new_value}")

        new_raw = "\n".join(new_lines).rstrip("\n") + "\n"

        if old_raw == new_raw:
            return backup_dir, []

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_raw, encoding="utf-8")

        try:
            os.chown(path, 1000, 1000)
        except Exception:
            pass

        return backup_dir, changed

    # Fallback old safe mode for any older form.
    lines = old_lines
    changed = []
    for meta in profile.get("keys", []):
        field = f"ini__{meta['section']}__{meta['key']}"
        if field not in request.form:
            continue
        new_value = _tools_ini_b2_validate_value(meta, request.form.get(field, ""))
        old_value = _tools_ini_b2_read_value(lines, meta["section"], meta["key"])
        if old_value != new_value:
            lines = _tools_ini_b2_set_key(lines, meta["section"], meta["key"], new_value)
            changed.append((meta["section"], meta["key"], old_value, new_value))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        os.chown(path, 1000, 1000)
    except Exception:
        pass

    return backup_dir, changed

# ---------------------------------------------------------------------------
# PinCabOS FINAL override: VPX/BGFX backend dropdown Linux only
# This is appended last on purpose. Python uses the last _tools_ini_full_field()
# definition, so this wins over older overrides without editing fragile blocks.
# ---------------------------------------------------------------------------

_TOOLS_INI_FULL_FIELD_BEFORE_LINUX_BACKEND_FINAL = _tools_ini_full_field

def _tools_ini_full_field(profile, section, key, value, idx):
    name = f"ini_value_{idx}"
    key_l = str(key or "").strip().lower()
    section_l = str(section or "").strip().lower()
    val = str(value or "").strip()

    backend_keys = {
        "gfxbackend",
        "graphicsbackend",
        "backend",
        "renderbackend",
        "renderer",
        "videobackend",
    }

    backend_sections = {
        "standalone",
        "video",
        "graphics",
        "bgfx",
    }

    # Force Linux-only backend choices for VPX/BGFX backend keys.
    if profile == "vpx" and key_l in backend_keys and (section_l in backend_sections or section_l):
        choices = ["OpenGL", "Vulkan", "GLES"]

        # If the current INI has an old unsupported value, show it but do not add Windows/macOS choices.
        if val and val not in choices:
            choices = [val] + choices

        labels = {
            "OpenGL": "OpenGL — Linux safe",
            "Vulkan": "Vulkan — Linux/BGFX test",
            "GLES": "GLES — Linux embedded",
        }

        html = ['<select name="' + _tools_esc(name) + '">']
        for choice in choices:
            selected = " selected" if choice == val else ""
            label = labels.get(choice, choice + " — valeur actuelle non standard")
            html.append(
                '<option value="'
                + _tools_esc(choice)
                + '"'
                + selected
                + ">"
                + _tools_esc(label)
                + "</option>"
            )
        html.append("</select>")
        return "".join(html)

    return _TOOLS_INI_FULL_FIELD_BEFORE_LINUX_BACKEND_FINAL(profile, section, key, value, idx)


_TOOLS_INI_DESCRIPTION_BEFORE_LINUX_BACKEND_FINAL = _tools_ini_description

def _tools_ini_description(profile, section, key):
    key_l = str(key or "").strip().lower()
    section_l = str(section or "").strip().lower()

    if profile == "vpx" and key_l in {
        "gfxbackend",
        "graphicsbackend",
        "backend",
        "renderbackend",
        "renderer",
        "videobackend",
    } and section_l in {
        "standalone",
        "video",
        "graphics",
        "bgfx",
    }:
        return (
            "VPX/BGFX graphics backend for PinCabOS Linux. "
            "Allowed Linux choices: OpenGL, Vulkan, GLES. "
            "OpenGL is the safe/default choice; Vulkan is for BGFX testing when the GPU driver supports it; "
            "GLES is mostly for embedded Linux targets."
        )

    return _TOOLS_INI_DESCRIPTION_BEFORE_LINUX_BACKEND_FINAL(profile, section, key)

# ---------------------------------------------------------------------------
# PinCabOS FINAL override: hide screen/DMD PinCabOS runtime sections from INI UI
# These sections are runtime screen metadata and must not be edited in VPX/VPinFE
# INI pages. They belong to the screen/GPU tools, not the manual INI editor.
# ---------------------------------------------------------------------------

_TOOLS_INI_PAGE_HTML_BEFORE_HIDE_RUNTIME_SCREEN_SECTIONS = _tools_ini_page_html

def _tools_ini_page_html(title, subtitle, profile, ini_path):
    path = Path(ini_path)

    hidden_runtime_sections = {
        "pincabos.fulldmd",
        "pincabos.screens",
        "pincabos.dmd",
    }

    if path.exists():
        try:
            raw = path.read_text(errors="replace").splitlines()
            out = []
            skip = False

            for line in raw:
                stripped = line.strip()
                m = re.match(r'^\[(.+?)\]\s*$', stripped)

                if m:
                    section_l = m.group(1).strip().lower()
                    if section_l in hidden_runtime_sections:
                        skip = True
                        continue
                    skip = False
                    out.append(line)
                    continue

                if skip:
                    continue

                out.append(line)

            if out != raw:
                temp_path = Path("/tmp/pincabos_ini_editor_filtered_" + profile + ".ini")
                temp_path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
                return _TOOLS_INI_PAGE_HTML_BEFORE_HIDE_RUNTIME_SCREEN_SECTIONS(title, subtitle, profile, temp_path)
        except Exception:
            pass

    return _TOOLS_INI_PAGE_HTML_BEFORE_HIDE_RUNTIME_SCREEN_SECTIONS(title, subtitle, profile, ini_path)

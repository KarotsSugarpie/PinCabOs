# PinCabOS WebApp module: Inputs / HID / Map Commander.
# Generated from the monolithic app.py refactor.
# The host app injects legacy shared helpers during register().
from __future__ import annotations

import glob
import html
import json
import os
import re
import shlex
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

from flask import jsonify, redirect, request, send_file, session, url_for

ROUTES: list[tuple[str, dict, object]] = []
BEFORE_REQUESTS: list[object] = []
AFTER_REQUESTS: list[object] = []

def route(rule: str, **options):
    """Record a Flask route locally; register() attaches it to the host app."""
    def decorator(func):
        ROUTES.append((rule, options, func))
        return func
    return decorator

def before_request(func):
    BEFORE_REQUESTS.append(func)
    return func

def after_request(func):
    AFTER_REQUESTS.append(func)
    return func

def register(host_app, runtime_globals: dict):
    """Bind shared helpers once, then register module-owned routes unchanged."""
    protected = {'ROUTES', 'route', 'register', '__name__', '__file__', '__package__'}
    for key, value in runtime_globals.items():
        if key not in protected:
            globals()[key] = value
    # Publish moved helpers back to the host namespace for legacy core pages that
    # still call them (for example page() -> firstrun_load_cfg()).
    prefixes = ("audio_", "ssf_", "inputs_", "firstrun_", "pincabos_", "PINCABOS_", "AUDIO_")
    for key, value in list(globals().items()):
        if key.startswith(prefixes):
            runtime_globals[key] = value
    for before_func in BEFORE_REQUESTS:
        host_app.before_request(before_func)
    for after_func in AFTER_REQUESTS:
        host_app.after_request(after_func)
    for rule, options, view_func in ROUTES:
        host_app.add_url_rule(rule, endpoint=view_func.__name__, view_func=view_func, **options)



PINCABOS_INPUTS_INI = "/home/pinball/.vpinball/VPinballX.ini"


PINCABOS_INPUTS_CFG = "/opt/pincabos/config/inputs-commander.json"


PINCABOS_INPUT_KEYMAP = [
    ("LeftFlipperKey", "Flipper gauche", "42"),
    ("RightFlipperKey", "Flipper droit", "54"),
    ("StagedLeftFlipperKey", "Flipper gauche staged / upper", ""),
    ("StagedRightFlipperKey", "Flipper droit staged / upper", ""),
    ("LeftMagnaSave", "Magna Save gauche", "29"),
    ("RightMagnaSave", "Magna Save droit", "97"),
    ("LeftMagnaSave2", "Magna Save gauche 2", ""),
    ("RightMagnaSave2", "Magna Save droit 2", ""),
    ("StartGameKey", "Start", "2"),
    ("StartGameKey2", "Start 2", ""),
    ("AddCreditKey", "Coin / crédit", "6"),
    ("AddCreditKey2", "Coin / crédit 2", ""),
    ("PlungerKey", "Plunger / Launch Ball", "28"),
    ("LockbarKey", "Lockbar Fire", ""),
    ("ExitGameKey", "Exit", "1"),
    ("PauseKey", "Pause", ""),
    ("LeftTiltKey", "Nudge gauche digital", "44"),
    ("RightTiltKey", "Nudge droite digital", "53"),
    ("CenterTiltKey", "Nudge centre digital", "57"),
    ("MechanicalTilt", "Tilt mécanique", "20"),
    ("VolumeUpKey", "Volume +", ""),
    ("VolumeDownKey", "Volume -", ""),
    ("CoinDoorKey", "Coin Door", ""),
    ("ServiceCancelKey", "Service Cancel", ""),
    ("ServiceDownKey", "Service Down", ""),
    ("ServiceUpKey", "Service Up", ""),
    ("ServiceEnterKey", "Service Enter", ""),
    ("BuyInKey", "Buy In / Extra Ball", ""),
    ("FrameCountKey", "Frame Counter / FPS", ""),
    ("DebuggerKey", "Debugger", ""),
    ("Enable3DKey", "Activer 3D", ""),
    ("JoyCustom1Key", "Custom 1", "22"),
    ("JoyCustom2Key", "Custom 2", "23"),
    ("JoyCustom3Key", "Custom 3", "24"),
    ("JoyCustom4Key", "Custom 4", "25"),
]


PINCABOS_INPUT_PLAYERMAP = [
    ("PBWEnabled", "Nudge analogique VPX activé", "0"),
    ("NudgeStrength", "Force visuelle du nudge", "0.01"),
    ("PlungerAxis", "Axe plunger VPX", ""),
]


PINCABOS_INPUTS_DEFAULT_CFG = {
    "input_mode": "auto",
    "capture_backend": "evdev",
    "preferred_device": "",
    "dudes_profile": "off",
    "dudes_shift_enabled": False,
    "dudes_shift_input": "",
    "dudes_nightmode_input": "",
    "stabilization_delay_ms": 20,
    "nudge_axis_x": "",
    "nudge_axis_y": "",
    "nudge_axis_z": "",
    "nudge_deadzone": "0.08",
    "nudge_gain_x": "1.0",
    "nudge_gain_y": "1.0",
    "nudge_invert_x": False,
    "nudge_invert_y": False,
    "virtual_tilt_enabled": False,
    "virtual_tilt_threshold": "0.85",
    "plunger_min": "0",
    "plunger_max": "65535",
    "plunger_invert": False,
    "launch_ball_emulation": "off",
}


def inputs_esc(value):
    import html
    return html.escape(str(value if value is not None else ""), quote=True)


def inputs_cmd(cmd, timeout=5):
    import subprocess
    try:
        r = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return str(e)


def inputs_load_cfg():
    from pathlib import Path
    import json
    cfg = dict(PINCABOS_INPUTS_DEFAULT_CFG)
    p = Path(PINCABOS_INPUTS_CFG)
    if p.exists():
        try:
            data = json.loads(p.read_text(errors="replace"))
            if isinstance(data, dict):
                cfg.update(data)
        except Exception:
            pass
    return cfg


def inputs_save_cfg(cfg):
    from pathlib import Path
    import json
    import subprocess
    p = Path(PINCABOS_INPUTS_CFG)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + chr(10))
    try:
        subprocess.run(["chown", "pinball:pinball", str(p)], timeout=10)
    except Exception:
        pass


def inputs_read_ini():
    from pathlib import Path
    p = Path(PINCABOS_INPUTS_INI)
    lines = p.read_text(errors="replace").splitlines() if p.exists() else []
    found = {}
    section = ""
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s.strip("[]")
            continue
        if "=" in line and not s.startswith((";", "#")):
            k, v = line.split("=", 1)
            found[k.strip()] = {"value": v.strip(), "section": section}
    return lines, found


def inputs_find_section(lines, wanted):
    for i, line in enumerate(lines):
        if line.strip().lower() == "[" + wanted.lower() + "]":
            end = len(lines)
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s.startswith("[") and s.endswith("]"):
                    end = j
                    break
            return i, end
    return None, None


def inputs_rewrite_ini(key_values, player_values):
    from pathlib import Path
    from datetime import datetime
    import shutil
    import subprocess

    ini = Path(PINCABOS_INPUTS_INI)
    if not ini.exists():
        raise FileNotFoundError(str(ini))

    backup_dir = Path("/opt/pincabos/backups/inputs-commander")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"VPinballX.ini.backup-inputs-commander-{stamp}"
    shutil.copy2(ini, backup)

    lines, found = inputs_read_ini()

    keyboard_section = "Keyboard"
    for probe in ["AddCreditKey", "LeftFlipperKey", "RightFlipperKey", "StartGameKey"]:
        if probe in found and found[probe].get("section"):
            keyboard_section = found[probe]["section"]
            break

    def rewrite_section(section_name, values, managed_keys, label):
        nonlocal lines
        start, end = inputs_find_section(lines, section_name)
        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append("[" + section_name + "]")
            start = len(lines) - 1
            end = len(lines)

        before = lines[:start + 1]
        section = lines[start + 1:end]
        after = lines[end:]

        cleaned = []
        for line in section:
            stripped = line.strip()
            if "PinCabOS fonction(Inputs Commander" in line:
                continue
            if "=" in line and not stripped.startswith((";", "#")):
                key = line.split("=", 1)[0].strip()
                if key in managed_keys:
                    continue
            cleaned.append(line)

        while cleaned and not cleaned[-1].strip():
            cleaned.pop()
        if cleaned:
            cleaned.append("")

        comment = "; Modifié " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " par PinCabOS fonction(" + label + ")"
        new_part = [comment]
        for key in managed_keys:
            new_part.append(key + " = " + str(values.get(key, "")))

        lines = before + cleaned + new_part + after

    keyboard_keys = [k for k, label, default in PINCABOS_INPUT_KEYMAP]
    player_keys = [k for k, label, default in PINCABOS_INPUT_PLAYERMAP]

    rewrite_section(keyboard_section, key_values, keyboard_keys, "Inputs Commander Keyboard")
    rewrite_section("Player", player_values, player_keys, "Inputs Commander Nudge")

    ini.write_text(chr(10).join(lines) + chr(10))
    try:
        subprocess.run(["chown", "pinball:pinball", str(ini)], timeout=10)
    except Exception:
        pass

    return str(backup), keyboard_section


def inputs_select(name, current, choices):
    out = ['<select name="' + inputs_esc(name) + '">']
    for value, label in choices:
        sel = " selected" if str(current) == str(value) else ""
        out.append('<option value="' + inputs_esc(value) + '"' + sel + ">" + inputs_esc(label) + "</option>")
    out.append("</select>")
    return "".join(out)


def inputs_checked(cfg, key):
    return "checked" if cfg.get(key) else ""


def inputs_devices_html():
    raw_proc = inputs_cmd("cat /proc/bus/input/devices 2>/dev/null || true", 5)
    raw_byid = inputs_cmd("ls -lah /dev/input/by-id 2>/dev/null || true", 5)
    raw_dev = inputs_cmd("ls -lah /dev/input/event* /dev/input/js* 2>/dev/null || true", 5)
    raw_usb = inputs_cmd("lsusb 2>/dev/null || true", 5)

    rows = []
    block = []
    for line in raw_proc.splitlines() + [""]:
        if line.strip():
            block.append(line)
            continue
        if not block:
            continue
        name = ""
        handlers = ""
        phys = ""
        for b in block:
            if b.startswith("N: Name="):
                name = b.split("=", 1)[1].strip().strip('"')
            elif b.startswith("H: Handlers="):
                handlers = b.split("=", 1)[1].strip()
            elif b.startswith("P: Phys="):
                phys = b.split("=", 1)[1].strip()
        if name or handlers:
            rows.append("<tr><td>" + inputs_esc(name) + "</td><td><code>" + inputs_esc(handlers) + "</code></td><td><code>" + inputs_esc(phys) + "</code></td></tr>")
        block = []

    table = "<p class='warn'>Aucun périphérique input détecté.</p>"
    if rows:
        table = "<table><tr><th>Périphérique</th><th>Handlers</th><th>Phys</th></tr>" + "".join(rows) + "</table>"

    return """
<div class="card">
  <h2>Périphériques HID / evdev détectés</h2>
  """ + table + """
  <details><summary>Voir /dev/input/by-id</summary><pre>""" + inputs_esc(raw_byid) + """</pre></details>
  <details><summary>Voir /dev/input/event* et js*</summary><pre>""" + inputs_esc(raw_dev) + """</pre></details>
  <details><summary>Voir lsusb</summary><pre>""" + inputs_esc(raw_usb) + """</pre></details>
  <details><summary>Voir /proc/bus/input/devices complet</summary><pre>""" + inputs_esc(raw_proc) + """</pre></details>
</div>
"""


@route("/inputs")
def inputs_page():
    body = """
<div class="card">
  <h1>Inputs</h1>
  <p>
    Gestion des entrées du pincab : boutons, plunger, nudge, tilt, magna save,
    coin, start, exit, HID, raw input, gamepad/XInput et Dude’s Cab.
  </p>

  <p>
    <a class="button" href="/inputs/map-commander">🎛️ Ouvrir Map Commander</a>
  </p>
</div>

<div class="card">
  <h2>Entrées PinCabOS</h2>
  <table>
    <tr><td>Boutons cabinet</td><td>Flippers, Start, Coin, Exit, Launch Ball, Magna Save, Tilt</td></tr>
    <tr><td>Nudge analogique</td><td>Axes X/Y/Z, deadzone, gain, inversion, virtual tilt</td></tr>
    <tr><td>Plunger</td><td>Axe VPX, calibration min/max, inversion, launch ball</td></tr>
  </table>
</div>
"""
    return page("Inputs", body)


@route("/inputs/map-commander")
def inputs_map_commander_page():
    cfg = inputs_load_cfg()
    lines, found = inputs_read_ini()

    key_rows = []
    for idx, (key, label, default) in enumerate(PINCABOS_INPUT_KEYMAP):
        current = found.get(key, {}).get("value", default)
        section = found.get(key, {}).get("section", "auto")
        status = "Détecté" if key in found else "Défaut"
        status_class = "good" if key in found else "warn"
        row = """
<tr>
  <td class="map-func"><strong>""" + inputs_esc(label) + """</strong></td>
  <td class="map-key"><code>""" + inputs_esc(key) + """</code></td>
  <td class="map-raw"><input id="raw_""" + inputs_esc(key) + """" class="map-raw-input" value="" readonly></td>
  <td class="map-value"><input id="key_""" + inputs_esc(key) + """" name="key_""" + inputs_esc(key) + """" value=\"""" + inputs_esc(current) + """" class="map-code-input"></td>
  <td class="map-section"><code>""" + inputs_esc(section) + """</code></td>
  <td class="map-state"><span class=\"""" + status_class + """\">""" + inputs_esc(status) + """</span></td>
  <td class="map-actions"><button class="button secondary map-mini-btn" type="button" onclick="detectInput('key_""" + inputs_esc(key) + """')">Détecter</button><button class="button secondary map-mini-btn" type="button" onclick="clearInput('key_""" + inputs_esc(key) + """')">Clear</button></td>
</tr>
"""
        key_rows.append(row)

    player_rows = []
    for key, label, default in PINCABOS_INPUT_PLAYERMAP:
        current = found.get(key, {}).get("value", default)
        section = found.get(key, {}).get("section", "Player")
        status = "Détecté" if key in found else "Défaut"
        status_class = "good" if key in found else "warn"
        player_rows.append("""
<tr>
  <td class="map-func"><strong>""" + inputs_esc(label) + """</strong></td>
  <td class="map-key"><code>""" + inputs_esc(key) + """</code></td>
  <td class="map-value"><input name="player_""" + inputs_esc(key) + """" value=\"""" + inputs_esc(current) + """" class="map-code-input"></td>
  <td class="map-section"><code>""" + inputs_esc(section) + """</code></td>
  <td class="map-state"><span class=\"""" + status_class + """\">""" + inputs_esc(status) + """</span></td>
</tr>
""")

    body = """
<style>
.map-grid {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(260px, 1fr);
  gap: 14px;
}
.map-key-columns {
  display: grid;
  grid-template-columns: minmax(480px, 1fr) minmax(480px, 1fr);
  gap: 14px;
  align-items: start;
}
.map-key-column {
  border: 1px solid rgba(255,176,0,.22);
  border-radius: 14px;
  padding: 10px;
  background: rgba(0,0,0,.14);
}
.map-key-column h3 {
  margin-top: 0;
  color: var(--pco-appearance-accent, #ffb000);
}
.map-box {
  border: 1px solid rgba(255,176,0,.25);
  border-radius: 14px;
  padding: 14px;
  background: rgba(0,0,0,.18);
}
.map-table-wrap { overflow-x: auto; }
.map-table {
  width: 100%;
  border-collapse: collapse;
}
.map-table th, .map-table td {
  vertical-align: middle;
  padding: 10px;
}
.map-table th { text-align:left; color:#ffb000; }
.map-func { min-width: 210px; }
.map-key { min-width: 190px; }
.map-value { width: 120px; text-align:center; }
.map-section { width: 100px; text-align:center; }
.map-state { width: 100px; text-align:center; }
.map-actions { width: 190px; white-space:nowrap; text-align:right; }
.map-code-input {
  width: 90px;
  text-align: center;
  font-family: monospace;
}
.map-mini-btn {
  min-width: 76px !important;
  font-size: 12px !important;
  padding: 4px 7px !important;
  margin-left: 5px !important;
}
#map-detect-status {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: var(--pco-appearance-button-radius, 10px);
  background: rgba(255,176,0,.08);
  border: 1px solid rgba(255,176,0,.25);
}
@media (max-width: 850px) {
  .map-grid { grid-template-columns: 1fr; }
  .map-key-columns { grid-template-columns: 1fr; }
}

.map-raw { width: 170px; text-align:center; }
.map-raw-input { width:155px; text-align:center; font-family:monospace; opacity:.9; }
.map-detect-modal { position:fixed; inset:0; background:rgba(0,0,0,.72); z-index:99999; display:none; align-items:center; justify-content:center; }
.map-detect-box { width:min(520px,92vw); border:1px solid rgba(255,176,0,.55); border-radius:18px; padding:22px; background:rgba(20,0,30,.96); box-shadow:0 0 35px rgba(255,122,0,.28); text-align:center; }
.map-detect-count { font-size:54px; font-weight:900; color:#ffb000; margin:12px 0; }
.map-detect-raw { margin-top:12px; padding:10px; border-radius:10px; background:rgba(0,0,0,.35); font-family:monospace; }

</style>

<div class="card">
  <h1>Map Commander</h1>
  <p>
    Mapping des boutons, du nudge analogique et du plunger vers VPX Standalone.
  </p>
  <p>
    Fichier VPX : <code>""" + inputs_esc(PINCABOS_INPUTS_INI) + """</code><br>
    Config PinCabOS : <code>""" + inputs_esc(PINCABOS_INPUTS_CFG) + """</code>
  </p>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0;">
    <div style="border:1px solid rgba(255,176,0,.45);border-radius:14px;padding:12px;background:rgba(255,176,0,.08);box-shadow:0 0 18px rgba(255,122,0,.12);">
      <strong>⚠️ Configuration recommandée sur le cab</strong><br>
      PinCabOS suggère de faire la configuration Map Commander directement sur le cab,
      en utilisant les boutons <strong>Afficher sur le cab</strong> pour valider les entrées réelles.
    </div>

    <div style="border:1px solid rgba(255,176,0,.45);border-radius:14px;padding:12px;background:rgba(255,176,0,.08);box-shadow:0 0 18px rgba(255,122,0,.12);">
      <strong>⚡ Conseil performance / latence</strong><br>
      PinCabOS suggère, si possible, d’utiliser un mapping <strong>clavier</strong>
      plutôt qu’un mapping joystick, surtout pour réduire la latence des boutons critiques.
    </div>
  </div>

  <p><a class="button secondary" href="/inputs">← Retour Inputs</a></p>
</div>

<form method="post" action="/inputs/save">

<div class="card">
  <h2>Mapping boutons VPX</h2>
  <p>Ces valeurs écrivent les codes dans <code>VPinballX.ini</code>.</p>
  <div class="map-table-wrap">
    <table class="map-table">
      <tr><th>Fonction</th><th>Clé VPX</th><th>Détecté brut</th><th>Valeur VPX</th><th>Section</th><th>État</th><th>Actions</th></tr>
      """ + "".join(key_rows) + """
    </table>
  </div>

<div class="map-detect-modal" id="mapDetectModal">
  <div class="map-detect-box">
    <h2>Détection en cours</h2>
    <p>Appuie sur une touche clavier dans cette page ou sur un bouton joystick.</p>
    <div class="map-detect-count" id="mapDetectCountdown">30</div>
    <div class="map-detect-raw" id="mapDetectRaw">En attente...</div>
    <p><button class="button secondary" type="button" onclick="closeDetectPopup()">Annuler</button></p>
  </div>
</div>

<script>
let mapDetectTimer = null;
let mapDetectKeyHandler = null;
let mapDetectActive = false;

function clearInput(id) {
  const el = document.getElementById(id);
  const rawEl = document.getElementById(id.replace("key_", "raw_"));
  if (el) {
    el.value = "";
    el.dispatchEvent(new Event("input", {bubbles:true}));
    el.focus();
  }
  if (rawEl) rawEl.value = "";
}

function closeDetectPopup() {
  mapDetectActive = false;

  const modal = document.getElementById("mapDetectModal");
  if (modal) modal.style.display = "none";

  if (mapDetectTimer) {
    clearInterval(mapDetectTimer);
    mapDetectTimer = null;
  }

  if (mapDetectKeyHandler) {
    window.removeEventListener("keydown", mapDetectKeyHandler, true);
    mapDetectKeyHandler = null;
  }
}

async function detectInput(id) {
  const el = document.getElementById(id);
  const rawEl = document.getElementById(id.replace("key_", "raw_"));
  const modal = document.getElementById("mapDetectModal");
  const countdown = document.getElementById("mapDetectCountdown");
  const rawBox = document.getElementById("mapDetectRaw");

  if (!el) return;

  const keyMap = {
    Escape:1,
    Digit1:2, Digit2:3, Digit3:4, Digit4:5, Digit5:6, Digit6:7, Digit7:8, Digit8:9, Digit9:10, Digit0:11,
    KeyQ:16, KeyW:17, KeyE:18, KeyR:19, KeyT:20, KeyY:21, KeyU:22, KeyI:23, KeyO:24, KeyP:25,
    KeyA:30, KeyS:31, KeyD:32, KeyF:33, KeyG:34, KeyH:35, KeyJ:36, KeyK:37, KeyL:38,
    KeyZ:44, KeyX:45, KeyC:46, KeyV:47, KeyB:48, KeyN:49, KeyM:50,
    Enter:28, Space:57,
    ShiftLeft:42, ShiftRight:54,
    ControlLeft:29, ControlRight:97,
    AltLeft:56, AltRight:100,
    ArrowLeft:105, ArrowRight:106, ArrowUp:103, ArrowDown:108,
    Insert:110, Delete:111, Home:102, End:107, PageUp:104, PageDown:109,
    F1:59, F2:60, F3:61, F4:62, F5:63, F6:64, F7:65, F8:66, F9:67, F10:68, F11:87, F12:88
  };

  mapDetectActive = true;
  let seconds = 30;

  if (modal) modal.style.display = "flex";
  if (countdown) countdown.textContent = seconds;
  if (rawBox) rawBox.textContent = "En attente...";
  el.focus();

  if (mapDetectTimer) clearInterval(mapDetectTimer);
  mapDetectTimer = setInterval(() => {
    seconds--;
    if (countdown) countdown.textContent = seconds;
    if (seconds <= 0) {
      if (rawBox) rawBox.textContent = "Timeout : aucune entrée détectée.";
      setTimeout(closeDetectPopup, 800);
    }
  }, 1000);

  function finish(code, raw) {
    if (!mapDetectActive) return;

    el.value = String(code);
    if (rawEl) rawEl.value = raw;
    if (rawBox) rawBox.textContent = raw + " -> VPX code " + code;

    setTimeout(closeDetectPopup, 700);
  }

  mapDetectKeyHandler = function(e) {
    if (!mapDetectActive) return;

    e.preventDefault();
    e.stopPropagation();

    const code = keyMap[e.code];
    const raw = "keyboard:web code=" + e.code + " key=" + e.key;

    if (code !== undefined) {
      finish(code, raw);
    } else if (rawBox) {
      rawBox.textContent = "Touche non mappée : " + raw;
    }
  };

  window.addEventListener("keydown", mapDetectKeyHandler, true);

  try {
    const r = await fetch("/inputs/detect-once", {method:"POST"});
    const data = await r.json();

    if (mapDetectActive && data.ok) {
      const raw = "evdev device=" + data.name + " code=" + data.code;
      finish(data.code, raw);
    }
  } catch(e) {
    if (rawBox) rawBox.textContent = "evdev non disponible, clavier web actif.";
  }
}
</script>

</div>

<div class="card">
  <h2>Nudge analogique / Plunger</h2>
  <p>Réglages analogiques VPX / PinCabOS.</p>

  <div class="np-grid-safe">
    <div class="np-panel-safe">
      <h3>🎯 Nudge X / Y</h3>
      <div class="nudge-scope-safe"><div class="nudge-dot-safe"></div></div>

      <div class="np-fields-safe">
        <label>Axe X <input name="nudge_axis_x" value=\"""" + inputs_esc(cfg.get("nudge_axis_x", "")) + """\"></label>
        <label class="checkline"><input type="checkbox" name="nudge_invert_x" value="1" """ + inputs_checked(cfg, "nudge_invert_x") + """> Inverser X</label>

        <label>Axe Y <input name="nudge_axis_y" value=\"""" + inputs_esc(cfg.get("nudge_axis_y", "")) + """\"></label>
        <label class="checkline"><input type="checkbox" name="nudge_invert_y" value="1" """ + inputs_checked(cfg, "nudge_invert_y") + """> Inverser Y</label>

        <label>Deadzone <input name="nudge_deadzone" value=\"""" + inputs_esc(cfg.get("nudge_deadzone", "0.08")) + """\"></label>
        <label>Max field <input name="nudge_maxfield" value=\"""" + inputs_esc(cfg.get("nudge_maxfield", "1.00")) + """\"></label>

        <label>Gain X <input name="nudge_gain_x" value=\"""" + inputs_esc(cfg.get("nudge_gain_x", "1.0")) + """\"></label>
        <label>Gain Y <input name="nudge_gain_y" value=\"""" + inputs_esc(cfg.get("nudge_gain_y", "1.0")) + """\"></label>

        <label class="checkline"><input type="checkbox" name="virtual_tilt_enabled" value="1" """ + inputs_checked(cfg, "virtual_tilt_enabled") + """> Virtual tilt</label>
        <label>Seuil tilt <input name="virtual_tilt_threshold" value=\"""" + inputs_esc(cfg.get("virtual_tilt_threshold", "0.85")) + """\"></label>
      </div>

      <p><button class="button" type="submit">Appliquer Nudge</button></p>
    </div>

    <div class="np-panel-safe">
      <h3>🕹️ Plunger Z</h3>
      <div class="plunger-track-safe"><div class="plunger-pointer-safe"></div></div>

      <div class="np-fields-safe">
        <label>Axe Z / Plunger <input name="nudge_axis_z" value=\"""" + inputs_esc(cfg.get("nudge_axis_z", "")) + """\"></label>
        <label>Deadzone plunger <input name="plunger_deadzone" value=\"""" + inputs_esc(cfg.get("plunger_deadzone", "0.03")) + """\"></label>

        <label>Min calibration <input name="plunger_min" value=\"""" + inputs_esc(cfg.get("plunger_min", "0")) + """\"></label>
        <label>Max calibration <input name="plunger_max" value=\"""" + inputs_esc(cfg.get("plunger_max", "65535")) + """\"></label>

        <label>Max field plunger <input name="plunger_maxfield" value=\"""" + inputs_esc(cfg.get("plunger_maxfield", "1.00")) + """\"></label>
        <label class="checkline"><input type="checkbox" name="plunger_invert" value="1" """ + inputs_checked(cfg, "plunger_invert") + """> Inverser plunger</label>

        <label>Émulation Launch Ball """ + inputs_select("launch_ball_emulation", cfg.get("launch_ball_emulation", "off"), [
          ("off", "Désactivée"),
          ("push", "Pousser à fond = Launch Ball"),
          ("pull", "Tirer à fond = Launch Ball"),
          ("both", "Pousser ou tirer = Launch Ball"),
      ]) + """</label>
      </div>

      <p><button class="button" type="submit">Appliquer Plunger</button></p>
    </div>
  </div>

  <details style="margin-top:16px;">
    <summary>Paramètres VPX dans [Player]</summary>
    <div class="map-table-wrap">
      <table class="map-table">
        <tr><th>Paramètre</th><th>Clé VPX</th><th>Valeur</th><th>Section</th><th>État</th></tr>
        """ + "".join(player_rows) + """
      </table>
    </div>
  </details>
</div>

<div class="card">
  <button class="button" type="submit">Sauvegarder Map Commander</button>
  
</div>

</form>
"""
    return page("Map Commander", body)


@route("/inputs/save", methods=["POST"])
def inputs_save():
    cfg = inputs_load_cfg()

    for key in [
        "input_mode",
        "capture_backend",
        "preferred_device",
        "dudes_profile",
        "dudes_shift_input",
        "dudes_nightmode_input",
        "nudge_axis_x",
        "nudge_axis_y",
        "nudge_axis_z",
        "nudge_deadzone",
        "nudge_gain_x",
        "nudge_gain_y",
        "virtual_tilt_threshold",
        "plunger_min",
        "plunger_max",
        "launch_ball_emulation",
        "stabilization_delay_ms",
    ]:
        cfg[key] = request.form.get(key, "").strip()

    for key in [
        "dudes_shift_enabled",
        "nudge_invert_x",
        "nudge_invert_y",
        "virtual_tilt_enabled",
        "plunger_invert",
    ]:
        cfg[key] = request.form.get(key) == "1"

    key_values = {}
    for key, label, default in PINCABOS_INPUT_KEYMAP:
        key_values[key] = request.form.get("key_" + key, "").strip()

    player_values = {}
    for key, label, default in PINCABOS_INPUT_PLAYERMAP:
        player_values[key] = request.form.get("player_" + key, "").strip()

    try:
        backup, keyboard_section = inputs_rewrite_ini(key_values, player_values)
        inputs_save_cfg(cfg)
        body = """
<div class="card">
  <h1>Inputs Commander sauvegardé</h1>
  <p class="good">Mapping écrit dans <code>""" + inputs_esc(PINCABOS_INPUTS_INI) + """</code>.</p>
  <p>Section clavier utilisée : <code>""" + inputs_esc(keyboard_section) + """</code></p>
  <p>Backup : <code>""" + inputs_esc(backup) + """</code></p>
  <a class="button" href="/inputs/map-commander">Retour Map Commander</a>
</div>
"""
        return page("Inputs", body)
    except Exception as e:
        body = """
<div class="card">
  <h1>Erreur Inputs Commander</h1>
  <p class="bad"><code>""" + inputs_esc(e) + """</code></p>
  <a class="button" href="/inputs">Retour</a>
</div>
"""
        return page("Inputs", body)


@route("/inputs/detect-once", methods=["POST"])
def inputs_detect_once():
    import os, glob, time, select, struct, json
    EVENT_FMT = "llHHI"
    EVENT_SIZE = struct.calcsize(EVENT_FMT)

    devices = []
    for dev in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
            devices.append((dev, fd))
        except Exception:
            pass

    if not devices:
        return jsonify({"ok": False, "error": "Aucun /dev/input/event* lisible. Vérifie les permissions du service PinCabOS."})

    try:
        deadline = time.time() + 8
        while time.time() < deadline:
            r, _, _ = select.select([fd for _, fd in devices], [], [], 0.25)
            for fd in r:
                try:
                    data = os.read(fd, EVENT_SIZE)
                    if len(data) != EVENT_SIZE:
                        continue
                    sec, usec, etype, code, value = struct.unpack(EVENT_FMT, data)
                    if etype == 1 and value == 1:
                        devname = next((d for d, f in devices if f == fd), "event")
                        return jsonify({"ok": True, "code": str(code), "name": devname})
                except Exception:
                    continue
        return jsonify({"ok": False, "error": "timeout"})
    finally:
        for _, fd in devices:
            try:
                os.close(fd)
            except Exception:
                pass


@route("/inputs/defaults", methods=["POST"])
def inputs_defaults():
    cfg = dict(PINCABOS_INPUTS_DEFAULT_CFG)
    inputs_save_cfg(cfg)

    key_values = {key: default for key, label, default in PINCABOS_INPUT_KEYMAP}
    player_values = {key: default for key, label, default in PINCABOS_INPUT_PLAYERMAP}

    try:
        backup, keyboard_section = inputs_rewrite_ini(key_values, player_values)
        body = """
<div class="card">
  <h1>Défauts Inputs appliqués</h1>
  <p class="good">Défauts PinCabOS appliqués.</p>
  <p>Section clavier utilisée : <code>""" + inputs_esc(keyboard_section) + """</code></p>
  <p>Backup : <code>""" + inputs_esc(backup) + """</code></p>
  <a class="button" href="/inputs/map-commander">Retour Map Commander</a>
</div>
"""
        return page("Inputs", body)
    except Exception as e:
        body = """
<div class="card">
  <h1>Erreur preset Inputs</h1>
  <p class="bad"><code>""" + inputs_esc(e) + """</code></p>
  <a class="button" href="/inputs">Retour</a>
</div>
"""
        return page("Inputs", body)
